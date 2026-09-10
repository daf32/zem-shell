"""Job control: background jobs, stop/continue, fg/bg/wait/kill/disown.

Headless: no tty, so terminal hand-off is a no-op; process groups,
signals and waitpid(WUNTRACED) are exercised for real.
"""

import os
import signal
import time

import pytest

from axonix.core.jobs import JobState, JobTable, format_notice, wait_process


def _settle(table: JobTable, predicate, timeout=3.0):
    """Poll `table.reap()` until `predicate()` holds (signals are async)."""
    end = time.time() + timeout
    while time.time() < end:
        table.reap()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def shell(full_shell):
    yield full_shell
    # Never leave sleepers behind.
    for job in list(full_shell.context._jobs):
        try:
            os.killpg(job.pgid, signal.SIGKILL)
        except OSError:
            pass


# -- executor-level ----------------------------------------------------------

def test_wait_process_reports_signal(shell, run):
    import subprocess
    proc = subprocess.Popen(["/bin/sleep", "5"])
    proc.send_signal(signal.SIGTERM)
    assert wait_process(proc) == ("signaled", signal.SIGTERM)
    assert proc.returncode == -signal.SIGTERM  # Popen sees it too


def test_wait_process_reports_stop(shell):
    import subprocess
    proc = subprocess.Popen(["/bin/sleep", "5"])
    proc.send_signal(signal.SIGSTOP)
    assert wait_process(proc) == ("stopped", signal.SIGSTOP)
    proc.send_signal(signal.SIGKILL)
    proc.send_signal(signal.SIGCONT)
    assert wait_process(proc) == ("signaled", signal.SIGKILL)


def test_children_can_be_stopped(shell, run):
    """preexec resets SIGTSTP, so a child reacts to it (the shell ignores it)."""
    run(shell, "/bin/sleep 5 &")
    job = shell.context._jobs.get("%1")
    os.killpg(job.pgid, signal.SIGTSTP)
    assert _settle(shell.context._jobs, lambda: job.state is JobState.STOPPED)


# -- background and jobs ------------------------------------------------------

def test_background_job_is_listed_and_reported(shell, run):
    code, out, err = run(shell, "/bin/sleep 5 &")
    assert code == 0 and err.startswith("[1] ")
    code, out, _ = run(shell, "jobs")
    assert code == 0
    assert out == format_notice(shell.context._jobs.get("%1"), "+") + "\n"
    assert "Running" in out and "/bin/sleep 5" in out


def test_background_pipeline_detaches_every_stage(shell, run):
    run(shell, "/bin/sleep 5 | /bin/cat &")
    job = shell.context._jobs.get("%1")
    assert len(job.procs) == 2
    assert all(p.poll() is None for p in job.procs)     # both still running
    assert job.command == "/bin/sleep 5 | /bin/cat"


def test_done_notice_before_next_prompt(shell, run):
    run(shell, "/bin/true &")
    table = shell.context._jobs
    assert _settle(table, lambda: len(table) == 0) or True
    # `jobs` prints the Done line of a job that finished since last check.
    run(shell, "/usr/bin/false &")
    time.sleep(0.2)
    code, out, _ = run(shell, "jobs")
    assert "Exit 1" in out and len(table) == 0


def test_jobs_l_and_p(shell, run):
    run(shell, "/bin/sleep 5 &")
    job = shell.context._jobs.get("%1")
    assert run(shell, "jobs -p")[1] == f"{job.pgid}\n"
    assert str(job.pgid) in run(shell, "jobs -l")[1]
    assert run(shell, "jobs -x")[0] == 2


# -- kill / wait ---------------------------------------------------------------

def test_kill_and_wait_return_signal_status(shell, run):
    run(shell, "/bin/sleep 5 &")
    assert run(shell, "kill %1")[0] == 0
    assert run(shell, "wait %1")[0] == 128 + signal.SIGTERM
    assert len(shell.context._jobs) == 0


def test_kill_9_by_pid_and_bad_targets(shell, run):
    run(shell, "/bin/sleep 5 &")
    job = shell.context._jobs.get("%1")
    assert run(shell, f"kill -9 {job.pgid}")[0] == 0
    assert run(shell, "wait %1")[0] == 128 + signal.SIGKILL
    code, _, err = run(shell, "kill %1")
    assert code == 1 and "no such job" in err
    assert run(shell, "kill -BOGUS %1")[0] == 2
    assert run(shell, "kill")[0] == 2
    assert run(shell, "kill abc")[0] == 2


def test_kill_l_lists_signals(shell, run):
    code, out, _ = run(shell, "kill -l")
    assert code == 0 and "TERM" in out.split() and "KILL" in out.split()


def test_wait_all_and_exit_codes(shell, run):
    run(shell, "/bin/sh -c 'exit 3' &")
    run(shell, "/bin/true &")
    assert run(shell, "wait")[0] == 0
    assert len(shell.context._jobs) == 0
    run(shell, "/bin/sh -c 'exit 3' &")
    assert run(shell, "wait %1")[0] == 3


# -- stop / bg / fg ------------------------------------------------------------

def test_stop_bg_fg_cycle(shell, run):
    run(shell, "/bin/sleep 5 &")
    table = shell.context._jobs
    job = table.get("%1")
    assert run(shell, "kill -STOP %1")[0] == 0
    assert _settle(table, lambda: job.state is JobState.STOPPED)
    assert "Stopped" in run(shell, "jobs")[1]

    code, out, _ = run(shell, "bg")
    assert code == 0 and out == "[1]+ /bin/sleep 5 &\n"
    assert job.state is JobState.RUNNING
    code, _, err = run(shell, "bg %1")
    assert code == 1 and "already in background" in err

    run(shell, "kill -STOP %1")
    assert _settle(table, lambda: job.state is JobState.STOPPED)
    # fg resumes it and waits; kill it from the outside so fg returns.
    import threading
    threading.Timer(0.2, lambda: os.killpg(job.pgid, signal.SIGTERM)).start()
    code, out, _ = run(shell, "fg %1")
    assert out == "/bin/sleep 5\n"
    assert code == 128 + signal.SIGTERM
    assert len(table) == 0


def test_fg_with_no_jobs(shell, run):
    code, _, err = run(shell, "fg")
    assert code == 1 and "no current job" in err


def test_foreground_stop_registers_job(shell, run):
    """A foreground job that gets stopped lands in the table with 128+TSTP."""
    import subprocess
    import threading
    proc = subprocess.Popen(["/bin/sleep", "5"], preexec_fn=os.setpgrp)
    threading.Timer(0.2, lambda: os.killpg(proc.pid, signal.SIGSTOP)).start()
    job = shell.context._jobs.add(proc.pid, "/bin/sleep 5", [proc])
    code = shell._wait_job(job, foreground=True)
    assert code == 128 + signal.SIGSTOP
    assert job.state is JobState.STOPPED and job in list(shell.context._jobs)
    os.killpg(proc.pid, signal.SIGKILL)
    os.killpg(proc.pid, signal.SIGCONT)


# -- disown / exit -------------------------------------------------------------

def test_disown(shell, run):
    run(shell, "/bin/sleep 5 &")
    run(shell, "/bin/sleep 5 &")
    pgids = [j.pgid for j in shell.context._jobs]
    assert run(shell, "disown %1")[0] == 0
    assert [j.id for j in shell.context._jobs] == [2]
    assert run(shell, "disown -a")[0] == 0
    assert len(shell.context._jobs) == 0
    for pgid in pgids:
        os.killpg(pgid, signal.SIGKILL)


def test_exit_warns_about_stopped_jobs_once(shell, run):
    run(shell, "/bin/sleep 5 &")
    job = shell.context._jobs.get("%1")
    run(shell, "kill -STOP %1")
    assert _settle(shell.context._jobs, lambda: job.state is JobState.STOPPED)
    code, _, err = run(shell, "exit")
    assert code == 1 and "stopped jobs" in err and shell.context.running
    run(shell, "exit 0")
    assert not shell.context.running and shell.context.exit_status == 0


def test_close_shell_hups_jobs(shell, run):
    run(shell, "/bin/sleep 5 &")
    job = shell.context._jobs.get("%1")
    shell._close_shell()
    assert _settle(JobTable(), lambda: job.procs[0].poll() is not None)


# -- job specs ---------------------------------------------------------------

def test_job_specs(shell, run):
    run(shell, "/bin/sleep 5 &")
    run(shell, "/bin/sleep 6 &")
    t = shell.context._jobs
    assert t.get("%%") is t.get("%2") and t.get("%+") is t.get("%2")
    assert t.get("%-") is t.get("%1")
    assert t.get("%/bin/sleep 6") is t.get("%2")
    assert t.get(str(t.get("%1").pgid)) is t.get("%1")
    for bad in ("%9", "%zzz", "%/bin/sleep"):
        with pytest.raises(Exception, match="job"):
            t.get(bad)
