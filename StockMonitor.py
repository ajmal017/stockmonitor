#!/usr/bin/env python3

import sys, time, traceback
from PyQt5 import QtWidgets as qws
from PyQt5 import QtCore as qcore

import yahoo_fin.stock_info as sinfo
import yfinance as yf

def GetYFinanceTicker(ticker : str):
    tkr = yf.Ticker(ticker)
    return tkr.info

#yahoo finance stock info package compiles way more reports in tabled formats from my viewing.
def GetStockPrice(ticker : str) -> float:
    return sinfo.get_live_price(ticker).item()
    # print(sinfo.get_analysts_info(ticker))
    # print(sinfo.get_balance_sheet(ticker))
    # print(sinfo.get_cash_flow(ticker))
    # print(sinfo.get_data(ticker,interval="1wk"))
    # gainers = sinfo.get_day_gainers()
    # print(type(gainers))
    # print(sinfo.get_quote_table(ticker))

class WorkerSignals(qcore.QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data
    
    error
        `tuple` (exctype, value, traceback.format_exc() )
    
    result
        `object` data returned from processing, anything

    progress
        `int` indicating % progress 

    '''
    finished = qcore.pyqtSignal()
    error = qcore.pyqtSignal(tuple)
    result = qcore.pyqtSignal(object)
    progress = qcore.pyqtSignal(int)

class Worker(qcore.QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and 
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()    

        # Add the callback to our kwargs
        self.kwargs['progress_callback'] = self.signals.progress  

    @qcore.pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


PORTFOLIO_YFINANCE_COLUMNS = ['Current Price', '% Today', 'Prev. Close', '52 Wk High', '52 Wk Low']
PORTFOLIO_TABLE_UPDATE_INTERVAL = 1000 * 12 # 10 seconds
PRICE_UPDATE_INTERVAL = 1000*11
CUR_PRICE_IDX   = 0
CUR_PERC_IDX    = 1
PREV_CLOSE_IDX  = 2
YRHIGH_IDX      = 3
YRLOW_IDX       = 4

PRICE_STR = "Current Price"
PERCENT_STR = "Day % Change"
PREV_CLOSE_STR = "Previous Close"
YRHIGH_STR = "52 Wk High"
YRLOW_STR = "52 Wk Low"


tickers = ['LOW','BAC','MSFT','AAPL','FB','DIS','GE','EPD','MPC','BP','DAL','MAR']

class Stock(object):
    def __init__(self, ticker):
        self.ticker = ticker
        self.price = -999
        self.close = self.price
        self.yrhigh = -999
        self.yrlow = -999
        self.historicalInfo = None
        self.infoList = None
        self.initialized = False

    def GetCurrentMetrics(self) -> list:
        return self.infoList

    def Initialize(self):
        try:
            # Get Current Stock Price
            stockPrice = GetStockPrice(self.ticker)
            self.price = stockPrice
        except Exception as e:
            print("Error: Unable to get stock price for {}: {}".format(self.ticker, e))

        try:
            # Get Historyical
            info = GetYFinanceTicker(self.ticker)
            self.historicalInfo = info
            self.close = info['regularMarketPreviousClose']
            self.todayChange = (100*self.price/self.close)-100
            self.close = info['regularMarketPreviousClose']
            self.yrhigh = info['fiftyTwoWeekHigh']
            self.yrlow  = info['fiftyTwoWeekLow']
            
            # !!! This is Dangerous, they should be indexed based on INT CONSTANTS !!!
            self.infoList = [self.price, self.todayChange, self.close, self.yrhigh, self.yrlow]

            print("Initialized")
            self.initialized = True
        except Exception as e:
            print("Error: Unable to get historical data for {}...{}".format(self.ticker, e))


    def Update(self):
        if not self.initialized:
            return self.Initialize()
        else:
            try:
                stockPrice = GetStockPrice(self.ticker)
                self.price = stockPrice
                self.todayChange =(100*self.price/self.close)-100
                self.infoList = [self.price, self.todayChange, self.close, self.yrhigh, self.yrlow]
            except Exception as e:
                print("Error: Unable to get price for {}...{}".format(self.ticker,e))

class StockMonitor(qws.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Monitor")
        self.resize(800,400)
        self.__mainLayout = qws.QVBoxLayout(self)


        self.marketMacros = qws.QLabel("DOW: {:.2f}, S&P: {:.2f}".format(GetStockPrice("^DJI"),GetStockPrice("^GSPC")))


        self.__mainLayout.addWidget(self.marketMacros)

        quitButton = qws.QPushButton("Quit")
        quitButton.clicked.connect(self.Quit)
        refreshButton = qws.QPushButton("Refresh")
        refreshButton.clicked.connect(self.Refresh)
        self.__mainLayout.addWidget(quitButton)
        self.__mainLayout.addWidget(refreshButton)
        self.InitializePortfolioTable()
        self.__mainLayout.addWidget(self.tableWidget)


        # Setup master stock dictionary
        self.stockDictionary = {}
        for ticker in tickers:
            self.stockDictionary[ticker] = Stock(ticker)

        self.threadpool = qcore.QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        # Pass the function to execute
        worker = Worker(self._priceUpdateThread) # Any other args, kwargs are passed to the run function
        worker.signals.finished.connect(self._updateThreadCompleteSignalHandler)
        worker.signals.progress.connect(self._updateThreadProgressSignalHandler)

        self.do_quit = False

        # Execute macro updater
        self.threadpool.start(worker) 
        self.num_threads_executing = 1

        self.timer = qcore.QTimer()
        self.timer.setInterval(PORTFOLIO_TABLE_UPDATE_INTERVAL)
        self.timer.timeout.connect(self._refreshPortfolioTableTimerHandler)
        self.timer.start()

    def Refresh(self):
        print("Refresh BUTTON CLICK!")
        self.__refreshPortfolioTable()

    def Quit(self):
        self.do_quit = True

    # Thread callbacks
    def _updateThreadProgressSignalHandler(self, n):
        # self.Refresh()
        pass

    def _refreshPortfolioTableTimerHandler(self):
        print("TIMER")
        self.__refreshPortfolioTable()

    def _priceUpdateThread(self, progress_callback):
        lastExecute = time.time()-6
        while not self.do_quit:
            if (time.time()-lastExecute) > PRICE_UPDATE_INTERVAL:
                self.__updateIndexes()
                self.__updateStockValues()
                lastExecute = time.time()

            time.sleep(1)

        return "Done."

    def _updateThreadCompleteSignalHandler(self):
        self.num_threads_executing -= 1
        print("THREAD COMPLETE!")
        if self.num_threads_executing == 0:
            sys.exit(0)

    def __updateIndexes(self):
        dowPrice = GetStockPrice("^DJI")
        sp500 = GetStockPrice("^GSPC")
        print(dowPrice, sp500)
        self.marketMacros.setText("DOW: {:.2f}, S&P: {:.2f}".format(dowPrice,sp500))

    def __updateStockValues(self):
        # This should pull data, store it as raw data, and update the QTableWidgetItem boxes for the corresponding 
        # table. To do this, the table items should be assigned to each stock class
        for ticker in tickers:
            print("Grabbing {}".format(ticker))
            self.stockDictionary[ticker].Update()
    
    def __refreshPortfolioTable(self):
        print("Refresh Portfolio Table")
        if len(self.stockDictionary.keys()) > 0:
            for ticker in self.stockDictionary.keys():
                row = tickers.index(ticker)
                metrics = self.stockDictionary[ticker].GetCurrentMetrics()
                if metrics is not None:
                    for column, dataPoint in enumerate(metrics):
                        print("Updating {}/{} with {}".format(row, column, dataPoint))
                        widgetItem = self.tableWidget.item(row, column)
                        widgetItem.setText("{:.2f}".format(dataPoint))
                        self.repaint(self.tableWidget.visualItemRect(widgetItem))

    def InitializePortfolioTable(self):
        self.tableWidget = qws.QTableWidget()
        self.tableWidget.setRowCount(len(tickers))
        self.tableWidget.setColumnCount(len(PORTFOLIO_YFINANCE_COLUMNS))
        self.tableWidget.setHorizontalHeaderLabels(PORTFOLIO_YFINANCE_COLUMNS)
        self.tableWidget.setVerticalHeaderLabels(tickers)
        self.tableWidget.setSizeAdjustPolicy(qws.QAbstractScrollArea.AdjustToContents)
        #singleStockFormLayout = qws.QGridLayout()
        for rowIndex, sTicker in enumerate(tickers):
            for columnIndex,key in enumerate(PORTFOLIO_YFINANCE_COLUMNS):
                self.tableWidget.setItem(rowIndex, columnIndex, qws.QTableWidgetItem(""))

            self.tableWidget.move(0,0)
def main():
    app = qws.QApplication(sys.argv)
    window = StockMonitor()
    window.show()
    app.exec_()



if __name__ == '__main__':
    main()