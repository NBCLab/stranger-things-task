"""
Heavily adapted from https://github.com/courtois-neuromod/task_stimuli/blob/714cdbceb4991c9eab43a33e34aae0a2b148548d/src/tasks/video.py
Make sure to give credit to the authors.
"""
import re
import os
import os.path as op
from glob import glob
import sys
import time
from datetime import datetime
import pandas as pd
import numpy as np

import serial

import psychopy
from psychopy import core, event, gui, visual, sound, data, logging
from psychopy.constants import STARTED, STOPPED  # pylint: disable=E0401

T_R = 1.5
START_FIX_DUR = T_R * 2
END_FIX_DUR = T_R * 3
END_SCREEN_DURATION = 2


def close_on_esc(win):
    """
    Closes window if escape is pressed
    """
    if 'escape' in event.getKeys():
        win.close()
        core.quit()


def draw(win, stim, duration, clock):
    """
    Draw stimulus for a given duration.

    Parameters
    ----------
    win : (visual.Window)
    stim : object with `.draw()` method
    duration : (numeric) duration in seconds to display the stimulus
    """
    # Use a busy loop instead of sleeping so we can exit early if need be.
    start_time = time.time()
    response = event.BuilderKeyResponse()
    response.tStart = start_time
    response.frameNStart = 0
    response.status = STARTED
    window.callOnFlip(response.clock.reset)
    event.clearEvents(eventType='keyboard')
    while time.time() - start_time < duration:
        stim.draw()
        keys = event.getKeys(keyList=['1', '2'],
                                      timeStamped=clock)
        if keys:
            response.keys.extend(keys)
            response.rt.append(response.clock.getTime())
        close_on_esc(win)
        win.flip()
    response.status = STOPPED
    return response.keys, response.rt


if __name__ == '__main__':
    # Ensure that relative paths start from the same directory as this script
    try:
        script_dir = op.dirname(op.abspath(__file__)).decode(sys.getfilesystemencoding())
    except AttributeError:
        script_dir = op.dirname(op.abspath(__file__))

    # Collect user input
    # ------------------
    # Remember to turn fullscr to True for the real deal.
    stim_dir = op.abspath(op.join(script_dir, 'stimuli'))

    all_stimuli = []
    for root, dirs, files in os.walk(stim_dir, topdown=True):
        mp4s = [op.join(root, f) for f in files if f.endswith('mp4')]
        all_stimuli += mp4s

    all_stim_dirs = sorted(list(set([op.dirname(f) for f in all_stimuli])))
    stimuli_groups = [sd.replace(stim_dir, '').lstrip(op.sep) for sd in all_stim_dirs]

    exp_info = {'Subject': '',
                'Session': '',
                'Film': stimuli_groups,
                'BioPac': ['No', 'Yes']}
    dlg = gui.DlgFromDict(
        exp_info,
        title='Session {0}'.format(exp_info['Session']),
        order=['Subject', 'Session', 'Film', 'BioPac'])
    window = visual.Window(
        fullscr=False,
        size=(800, 600),
        monitor='testMonitor',
        units='norm',
        allowStencil=False,
        allowGUI=False,
        color='black',
        colorSpace='rgb',
        blendMode='avg',
        useFBO=True)
    fps = 1 / window.monitorFramePeriod
    if not dlg.OK:
        core.quit()

    if exp_info['BioPac'] == 'Yes':
        ser = serial.Serial('COM2', 115200)

    video_files = sorted(glob(op.join(stim_dir, exp_info['Film'], '*.mp4')))
    stim_dict = {}
    for video_file in video_files:
        runs_found = re.findall('(R[0-9]+)\.', op.basename(video_file))
        if not runs_found:
            raise Exception('Run number could not be found for {}'.format(video_file))
        elif len(runs_found) > 1:
            raise Exception('Run number could not be determined for {}'.format(video_file))
        else:
            run_num = runs_found[0][1:]  # drop the R
            stim_dict[run_num] = video_file

    waiting = visual.TextStim(
        window,
        """\
You are about to watch a video.
  Please keep your eyes open.""",
        name='instructions',
        color='white')
    end_screen = visual.TextStim(
        window,
        "The task is now complete.",
        name='end_screen',
        color='white')
    crosshair = visual.TextStim(
        window,
        '+',
        height=2,
        name='crosshair',
        color='white')

    if not op.exists(op.join(script_dir, 'data')):
        os.makedirs(op.join(script_dir, 'data'))

    run_clock = core.Clock()

    for run_label, video_file in stim_dict.items():
        COLUMNS = ['onset', 'duration', 'trial_type', 'stim_file']
        run_data = {c: [] for c in COLUMNS}
        video_filename = op.basename(video_file)
        task_label = video_filename.split('R{}'.format(run_label))[0]
        filename = op.join(
            script_dir, 'data',
            'sub-{0}_ses-{1}_task-{2}_run-{3}_events'.format(
                exp_info['Subject'].zfill(2),
                exp_info['Session'].zfill(2),
                task_label, run_label))
        outfile = filename + '.tsv'
        logfile = logging.LogFile(filename+'.log', level=logging.EXP)
        logging.console.setLevel(logging.WARNING)  # this outputs to the screen, not a file

        # Reset BioPac
        if exp_info['BioPac'] == 'Yes':
            ser.write('RR')
        video = visual.MovieStim(
            window,
            filename=video_file,
            name=exp_info['Film'])

        # Scanner runtime
        # ---------------
        # Wait for trigger from scanner.
        waiting.draw()
        window.flip()
        event.waitKeys(keyList=['5'])

        # Start recording
        if exp_info['BioPac'] == 'Yes':
            ser.write('FF')

        run_clock.reset()

        # Start with fixation
        startTimeFix1 = run_clock.getTime()
        draw(win=window, stim=crosshair, duration=START_FIX_DUR, clock=run_clock)

        # Now the video
        startTimeVid = run_clock.getTime()
        durationFix1 = startTimeVid - startTimeFix1

        # not sure what impact this has, if any
        video.autoDraw = False

        n_frames = int(np.ceil(video.duration * fps))
        # n_frames = int(np.ceil(10 * fps))  # test with 10 seconds
        for t in range(n_frames):
            video.draw(window)
            window.flip()
            close_on_esc(window)

        video.pause()

        startTimeFix2 = run_clock.getTime()
        durationVid = startTimeFix2 - startTimeVid

        # End with fixation. Scanner should stop after this.
        # Determine duration of ending fixation.
        upper = np.ceil(startTimeFix2 / T_R) * T_R
        diff = upper - startTimeFix2
        run_end_fix_dur = END_FIX_DUR + diff
        draw(win=window, stim=crosshair, duration=run_end_fix_dur, clock=run_clock)
        window.flip()

        startTimeEnd = run_clock.getTime()
        durationFix2 = startTimeEnd - startTimeFix2

        # Compile file
        run_data['onset'] = [startTimeFix1, startTimeVid, startTimeFix2]
        run_data['duration'] = [durationFix1, durationVid, durationFix2]
        run_data['trial_type'] = ['fixation', 'film', 'fixation']
        run_data['stim_file'] = ['n/a', video_file.split('/stimuli/')[1], 'n/a']

        # Save output file
        run_frame = pd.DataFrame(run_data)
        run_frame.to_csv(outfile, line_terminator='\n', sep='\t', na_rep='n/a', index=False)

        # Stop recording
        if exp_info['BioPac'] == 'Yes':
            ser.write('00')

        print('Total duration of run: {}'.format(run_clock.getTime()))
    # end run_loop

    # Shut down serial port connection
    if exp_info['BioPac'] == 'Yes':
        ser.close()

    # Final note that task is over. Runs after scan ends.
    draw(win=window, stim=end_screen, duration=END_SCREEN_DURATION, clock=run_clock)
    window.flip()

    logging.flush()

    # make sure everything is closed down
    del(waiting, end_screen, crosshair)
    window.close()
    core.quit()
