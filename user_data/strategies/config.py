class Config:
    BACKTEST_DOWNLOADED_JSON_DATA_FILE_PATH = ""
    BACKTEST_DATA_CLEANER_YEAR = 2020
    BACKTEST_DATA_CLEANER_MONTH_INDEX = 9
    IS_BACKTEST = False
    WORKSPACE_PATH = "workspace2" if IS_BACKTEST else "workspace"
    EXECUTION_PATH = "/root/" + WORKSPACE_PATH + "/execution/"
    IS_PARALLER_EXECUTION = True
