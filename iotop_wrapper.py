# iotop_wrapper.py
#
# SPDX-License-Identifier: MIT
#
# MIT License
#
# Copyright (c) 2019 Claudius Heine <ch AT denx DOT de>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the
# following conditions:
#
# The above copyright notice and this permission notice (including the next
# paragraph) shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
# NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
# USE OR OTHER DEALINGS IN THE SOFTWARE.

import collectd


DATA = {"interval": 5}


def worker(close_event, queue, interval):
    import subprocess
    import time
    from datetime import datetime, timedelta

    proc = None
    try:
        proc = subprocess.Popen(
            ["iotop", "-oqqtkd", str(interval)],
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        collectd.notice("iotop-worker: worker: iotop started")

        # Skip first two lines, since they contain the first statistic, that is
        # often wrong:
        proc.stdout.readline()
        proc.stdout.readline()

        while proc.returncode is None and not close_event.is_set():
            line = proc.stdout.readline().strip()

            if not line:
                collectd.info("iotop-worker: worker: EOL")
                break

            # Format of the iotop line:
            # 11:22:33 Actual DISK READ: 0.00 K/s | Actual DISK WRITE: 0.00 K/s

            # Skip everything that is not this line:
            if "Actual DISK READ" not in line:
                continue

            # Convert 'HH:MM:SS' to unix time (assumes that it on the current
            # day)
            now = datetime.now()

            ts = datetime.strptime(line.split()[0], "%H:%M:%S")
            ts = now.replace(
                hour=ts.hour, minute=ts.minute, second=ts.second, microsecond=0
            )

            # If the resulting time is in the future, substract days (normally
            # just one):
            while ts > now:
                ts = ts - timedelta(days=1)

            # If the timestamp is to old, just ignore it:
            if ts <= now - timedelta(days=1):
                continue

            # Convert it to unix time, without the microsecond floaty bits:
            ts = int(time.mktime(ts.timetuple()))

            # Convert XX.YY KB/s to a integer bitrate
            actual_read = int(float(line.split()[4]) * 1000 * 8)
            actual_write = int(float(line.split()[10]) * 1000 * 8)

            collectd.info("iotop-worker: worker: submitted to queue")
            # Put it in the queue:
            queue.put((ts, actual_read, actual_write))

    finally:
        queue.close()
        if proc and proc.returncode is None:
            try:
                collectd.notice("iotop-worker: worker: iotop kill")
                proc.kill()
                collectd.notice("iotop-worker: worker: iotop communicate")
                proc.communicate()
                collectd.notice("iotop-worker: worker: iotop close stdout")
                proc.stdout.close()
                collectd.notice("iotop-worker: worker: iotop wait")
                proc.wait()
                if proc.returncode is None:
                    proc.terminate()
            except OSError:
                # ignore errors when terminating iotop, we have done our best
                pass
        collectd.notice("iotop-worker: worker exits")


def config(config):
    for node in config.children:
        key = node.key.lower()
        val = node.values[0]

        if key == "interval":
            collectd.notice(
                "iotop-worker: config: got interval value %s" % (val)
            )
            DATA["interval"] = int(val)


def init(data):
    import multiprocessing as mp

    q = mp.Queue()
    e = mp.Event()
    p = mp.Process(target=worker, args=(e, q, data["interval"],))
    data["queue"] = q
    data["close_event"] = e
    data["process"] = p
    collectd.notice("iotop-worker: init: start process")
    p.start()


def shutdown(data):
    collectd.notice("iotop-worker: shutdown: start shutdown")
    data["close_event"].set()
    data["process"].join(timeout=data["interval"] + 1)
    if data["process"].is_alive():
        collectd.notice("iotop-worker: shutdown: worker needs terminating")
        data["process"].terminate()
        data["process"].join()
    data["queue"].close()


def read(data):
    collectd.info("iotop-worker: read: start read")
    import Queue as queue

    q = data["queue"]
    try:
        while True:
            item = q.get(block=False)
            collectd.info("iotop-worker: read: fetch element from queue")
            vl = collectd.Values(
                plugin="iotop_wrapper", time=item[0], type="bitrate"
            )
            vl.interval = data["interval"]
            vl.dispatch(type_instance="actual_read", values=(item[1],))
            vl.dispatch(type_instance="actual_write", values=(item[2],))
    except queue.Empty:
        pass


collectd.register_config(config)
collectd.register_init(init, data=DATA)
collectd.register_shutdown(shutdown, data=DATA)
collectd.register_read(read, data=DATA)
