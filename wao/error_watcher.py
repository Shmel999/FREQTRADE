import subprocess
import watchdog.events
import watchdog.observers
import sys

from wao.brain_config import BrainConfig


class Error_Watcher(watchdog.events.PatternMatchingEventHandler):

    def __init__(self):
        watchdog.events.PatternMatchingEventHandler.__init__(self,
                                                             ignore_directories=False, case_sensitive=False)

    def do_grep_cmd(self, file_name, grep_string):
        error_check_command = "grep " + grep_string + " " + file_name
        out_put_string = subprocess.run(error_check_command, shell=True, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        # out, err = result.communicate()
        # out_put_string = out.decode('latin-1')
        print("out_put_string: " + str(out_put_string))
        return str(out_put_string)

    def on_created(self, event):
        file_name = str(event.src_path)

        error_check_command = "grep error " + file_name + " && grep exception " \
                              + file_name + " && grep Error " + file_name + " && grep Exception " + file_name \
                              + file_name + " && grep ERROR " + file_name + " && grep EXCEPTION " + file_name
        result = subprocess.Popen([error_check_command],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, shell=True, executable='/bin/bash')
        out, err = result.communicate()
        out_put_string = out.decode('latin-1')
        if not self.__freqtrade_error_case(out_put_string):
            stop_bot_command = "python3 " + BrainConfig.EXECUTION_PATH + "/stop_bot.py " + str(
                BrainConfig.MODE) + " " + out_put_string.split("\n")[0].replace("_", "") \
                                   .replace(": ", ":").replace(" ", "#").replace("(", "").replace(")", "")
            result_log = subprocess.Popen([stop_bot_command],
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, shell=True, executable='/bin/bash')

            out, err = result_log.communicate()
            out_put = out.decode('latin-1')

    def on_modified(self, event):
        file_name = str(event.src_path)

        out_put_string = self.do_grep_cmd(file_name, "camera")
        if not self.__freqtrade_error_case(out_put_string):
            stop_bot_command = "python3 " + BrainConfig.EXECUTION_PATH + "/stop_bot.py " + str(
                BrainConfig.MODE) + " " + out_put_string.split("\n")[0].replace("_", "") \
                                   .replace(": ", ":").replace(" ", "#").replace("(", "").replace(")", "")
            result_log = subprocess.Popen([stop_bot_command],
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, shell=True, executable='/bin/bash')

            out, err = result_log.communicate()
            out_put = out.decode('latin-1')

    def __freqtrade_error_case(self, out_put_string):
        lower_string = out_put_string.lower()
        return "freqtrade" in lower_string and ("warning" in lower_string or "error" in lower_string)
