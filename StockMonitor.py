#!/usr/bin/env python3

import sys, time, traceback
from PyQt5 import QtWidgets as qws
from PyQt5 import QtCore as qcore

import yahoo_fin.stock_info as sinfo
import yfinance as yf
from datetime import datetime

from Datastore import Datastore, BUY_TRANSACTION, SELL_TRANSACTION

LOG_LEVEL_INFO = 0
LOG_LEVEL_DEBUG = 1
LOG_LEVEL = LOG_LEVEL_INFO


def INFO(string):
    if LOG_LEVEL >= LOG_LEVEL_INFO:
        print("INFO: {}".format(string))

def DEBUG(string):
    if LOG_LEVEL >= LOG_LEVEL_DEBUG:
        print("DEBUG: {}".format(string))


def GetHistoricalData(ticker : str):
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

PRICE_STR = "Current Price"
PERCENT_STR = "Day % Change"
PREV_CLOSE_STR = "Previous Close"
YRHIGH_STR = "52 Wk High"
YRLOW_STR = "52 Wk Low"
CUR_PRICE_IDX   = 0
CUR_PERC_IDX    = 1
PREV_CLOSE_IDX  = 2
YRHIGH_IDX      = 3
YRLOW_IDX       = 4

PORTFOLIO_YFINANCE_COLUMNS = [PRICE_STR, PERCENT_STR, PREV_CLOSE_STR, YRHIGH_STR, YRLOW_STR]
PORTFOLIO_DB_COLUMNS = ["# Shares", "Avg. Share Price", "Total Profit", "Days Profit"]

PORTFOLIO_TABLE_UPDATE_INTERVAL = 1000 * 12 # 10 seconds
PRICE_UPDATE_INTERVAL = 11



tickers = ['LOW','BAC','MSFT','AAPL','FB','DIS','GE','EPD','MPC','BP','DAL','MAR']

class Stock(object):
    def __init__(self, ticker, datastore):
        self.ticker = ticker
        self.price = -999
        self.close = self.price
        self.yrhigh = -999
        self.yrlow = -999
        self.historicalInfo = None
        self.infoList = [None for key in PORTFOLIO_YFINANCE_COLUMNS]
        self.dbList = [None for key in PORTFOLIO_DB_COLUMNS]
        self.initialized = False

        self.db = datastore
        self.position = self.db.GetPosition(self.ticker)
        INFO("stock got position {}".format(self.position))

    def GetCurrentMetrics(self) -> list:
        return self.infoList

    def GetDatabaseMetrics(self) -> list:
        return self.dbList

    def Initialize(self):
        try:
            # Get Current Stock Price
            stockPrice = GetStockPrice(self.ticker)
            self.price = stockPrice
        except Exception as e:
            print("Error: Unable to get stock price for {}: {}".format(self.ticker, e))

        try:
            # Get Historyical
            info = GetHistoricalData(self.ticker)
            self.historicalInfo = info
            self.close = info['regularMarketPreviousClose']
            self.todayChange = (100*self.price/self.close)-100
            self.close = info['regularMarketPreviousClose']
            self.yrhigh = info['fiftyTwoWeekHigh']
            self.yrlow  = info['fiftyTwoWeekLow']
            
            # !!! This is Dangerous, they should be indexed based on INT CONSTANTS !!!
            self.infoList = [self.price, self.todayChange, self.close, self.yrhigh, self.yrlow]
            if self.position:
                    # ["# Shares", "Avg. Share Price", "Total Profit", "Days Profit"]
                    avgPrice = self.position[2]
                    numshares = self.position[1]
                    dailyProfit = numshares*(self.price - self.close)
                    totalProfit = numshares*(self.price - avgPrice)
                    self.dbList = [numshares, avgPrice, totalProfit, dailyProfit]
            self.initialized = True
        except Exception as e:
            print("Error: Unable to get historical data for {}...{}".format(self.ticker, e))
            self.infoList = [self.price, None, None, None, None]

    def UpdatePosition(self,position):
        self.position = position

    def Update(self):
        if not self.initialized:
            return self.Initialize()
        else:
            try:
                stockPrice = GetStockPrice(self.ticker)
                self.price = stockPrice
                self.todayChange =(100*self.price/self.close)-100
                self.infoList = [self.price, self.todayChange, self.close, self.yrhigh, self.yrlow]

                if self.position:
                    # ["# Shares", "Avg. Share Price", "Total Profit", "Days Profit"]
                    avgPrice = self.position[2]
                    numshares = self.position[1]
                    dailyProfit = numshares*(self.price - self.close)
                    totalProfit = numshares*(self.price - avgPrice)
                    self.dbList = [numshares, avgPrice, totalProfit, dailyProfit]
            except Exception as e:
                print("Error: Unable to get price for {}...{}".format(self.ticker,e))


class TradeLogPopup(qws.QDialog):
    NumGridRows = 4
    NumButtons = 4
    def __init__(self, datastore):
        super().__init__()
        self.createFormGroupBox()
        
        self.db = datastore

        buttonBox = qws.QDialogButtonBox(qws.QDialogButtonBox.Ok | qws.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.validate)
        buttonBox.rejected.connect(self.reject)

        mainLayout = qws.QVBoxLayout()
        mainLayout.addWidget(self.formGroupBox)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)
        
        self.setWindowTitle("Log Trade")
        
    def validate(self):
        try:
            INFO("Validating...")
            ticker = self.tickerLineEdit.text()
            if len(ticker) <= 0:
                raise Exception("Ticker missing!")
            transactionType= self.buySellComboBox.currentText()
            price = self.priceLineEdit.text()
            pFloat = 0
            volume = int(self.volumeSpinBox.value())
            if volume <= 0:
                raise Exception("Volume must be greater than 0")
            try:
                pFloat = float(price)
                if pFloat <= 0:
                    raise Exception
            except Exception as e:
                raise Exception("Price must be integer above 0")
        except Exception as e:
            msgBox = qws.QMessageBox()
            msgBox.setIcon(qws.QMessageBox.Information)
            msgBox.setText("{}".format(e))
            msgBox.setWindowTitle("ERROR")
            msgBox.exec()
            return

        now = datetime.now()

        # dd/mm/YY H:M:S
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        INFO("Logging {}: {} {} @ {}...{}".format(transactionType, ticker, volume, pFloat, dt_string))

        # LogTrade(self, ticker, transaction, volume, price, date):
        self.db.LogTrade(ticker, transactionType, volume, pFloat, dt_string)
        self.accept()

    def createFormGroupBox(self):
        self.formGroupBox = qws.QGroupBox("Trade Log")
        layout = qws.QFormLayout()
        self.buySellComboBox = qws.QComboBox()
        self.buySellComboBox.addItems([BUY_TRANSACTION,SELL_TRANSACTION])
        self.tickerLineEdit=qws.QLineEdit()
        self.priceLineEdit = qws.QLineEdit()
        self.volumeSpinBox = qws.QSpinBox()

        layout.addRow(qws.QLabel("Ticker:"), self.tickerLineEdit)
        layout.addRow(qws.QLabel("Buy/Sell:"), self.buySellComboBox)
        layout.addRow(qws.QLabel("Price:"), self.priceLineEdit)
        layout.addRow(qws.QLabel("Volume:"), self.volumeSpinBox)
        self.formGroupBox.setLayout(layout)

class StockMonitor(qws.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Monitor")
        #self.resize(800,400)
        self.__mainLayout = qws.QVBoxLayout(self)

        # Make our database
        self.db = Datastore()

        # TODO - Move this/Adjust this/Somethings
        self.marketMacros = qws.QLabel("DOW: {:.2f}, S&P: {:.2f}".format(GetStockPrice("^DJI"),GetStockPrice("^GSPC")))
        self.__mainLayout.addWidget(self.marketMacros)

        # Quit Button
        quitButton = qws.QPushButton("Quit")
        quitButton.clicked.connect(self.Quit)

        # Log Trade Button
        tradeButton = qws.QPushButton("Log Trade")
        tradeButton.clicked.connect(self.LogTrade)

        # Setup master stock dictionary
        self.stockDictionary = {}
        self.masterPortfolioTickerList = []
        positions = self.db.GetAllPositions()
        for position in positions:
            ticker = position[0]
            self.masterPortfolioTickerList.append(ticker)
            self.stockDictionary[ticker] = Stock(ticker, self.db)


        self.InitializePortfolioTable()
        self.__mainLayout.addWidget(tradeButton)
        self.__mainLayout.addWidget(self.tableWidget)
        self.__mainLayout.addWidget(quitButton)


        menu = self.__createMenu()
        self.__mainLayout.setMenuBar(menu)

        self.threadpool = qcore.QThreadPool()
        INFO("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

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

        self.popup = TradeLogPopup(self.db)

    def LogTrade(self):
        # Make a dialogue box to get the info we want
        self.popup.show()

    def Refresh(self):
        INFO("Refresh BUTTON CLICK!")
        self.__refreshPortfolioTable()

    def Quit(self):
        DEBUG("!!!!!QUIT!!!!!!")
        self.do_quit = True
        if self.num_threads_executing == 0:
            sys.exit(0)

    def __createMenu(self):
        menu = qws.QMenuBar()
        actionMenu = menu.addMenu("Actions")

        refreshMenu = qws.QAction(menu)
        refreshMenu.setText("Refresh")
        refreshMenu.triggered.connect(self.Refresh)
        
        exitMenu = qws.QAction(menu)
        exitMenu.setText("Close")
        exitMenu.triggered.connect(self.Quit)

        actionMenu.addAction(refreshMenu)
        actionMenu.addAction(exitMenu)

        return menu

    # Thread callbacks
    def _updateThreadProgressSignalHandler(self, n):
        # self.Refresh()
        pass

    # This call happens within the main GUI thread. All SqliTE3 update
    # calls need to happen from this!
    def _refreshPortfolioTableTimerHandler(self):
        DEBUG("TIMER")
        self.__refreshPortfolioTable()

        # If a new BUY/SELL happens, the self.masterPortfolioTickerList needs to be updated. The 
        # main GUI also needs to be updated with the added/removed/edited row
        positions = self.db.GetAllPositions()

        tickers = [item[0] for item in positions]
        DEBUG("RefreshPortfolioTableView -> Found tickers {}".format(",".join(tickers)))
        DEBUG("RefreshPortfolioTableView -> Current tickers {}".format(",".join(self.masterPortfolioTickerList)))
        for position in positions:
            ticker = position[0]
            if ticker in self.masterPortfolioTickerList:
                # Update the Stocks position
                DEBUG("\tTelling stock {} to update position".format(position))
                self.stockDictionary[ticker].UpdatePosition(position)
            else:
                DEBUG("\tFound ticker not yet added! {}".format(ticker))
                # Stock is NOT alreay accounted for!
                self.masterPortfolioTickerList.append(ticker)
                self.stockDictionary[ticker] = Stock(ticker, self.db)
                rowIndex = self.masterPortfolioTickerList.index(ticker)
                self.tableWidget.insertRow(self.masterPortfolioTickerList.index(ticker))
                self.tableWidget.setVerticalHeaderLabels(self.masterPortfolioTickerList)
                for columnIndex,key in enumerate(PORTFOLIO_YFINANCE_COLUMNS+PORTFOLIO_DB_COLUMNS):
                    self.tableWidget.setItem(rowIndex, columnIndex, qws.QTableWidgetItem(""))
            
            # TODO: Find stocks that are no longer in the portfolio and remove them from the table!

    # This is a seperate thread. Only memory objects can be updated or amended,
    # and no FormLayout or QTableWidget items can be changed here
    def _priceUpdateThread(self, progress_callback):
        lastExecute = time.time()-PRICE_UPDATE_INTERVAL-1
        while not self.do_quit:
            if (time.time()-lastExecute) > PRICE_UPDATE_INTERVAL:
                self.__updateIndexes()
                self.__updateStockValues()
                lastExecute = time.time()

            time.sleep(1)

        return "Done."

    def _updateThreadCompleteSignalHandler(self):
        self.num_threads_executing -= 1
        DEBUG("THREAD COMPLETE!")
        if self.num_threads_executing == 0:
            sys.exit(0)

    def __updateIndexes(self):
        DEBUG("Updating indexes")
        dowPrice = GetStockPrice("^DJI")
        sp500 = GetStockPrice("^GSPC")
        self.marketMacros.setText("DOW: {:.2f}, S&P: {:.2f}".format(dowPrice,sp500))

    def __updateStockValues(self):
        # This should pull data, store it as raw data, and update the QTableWidgetItem boxes for the corresponding 
        # table. To do this, the table items should be assigned to each stock class
        startUpdateTime = time.time()
        for ticker in self.masterPortfolioTickerList:
            DEBUG("Grabbing {}".format(ticker))
            self.stockDictionary[ticker].Update()
            if self.do_quit:
                break
        INFO("Took {0:.2f} seconds to update stock prices".format(time.time()-startUpdateTime))
    
    def __refreshPortfolioTable(self):
        DEBUG("Refresh Portfolio Table")
        if len(self.masterPortfolioTickerList) > 0:
            for ticker in self.masterPortfolioTickerList:
                row = self.masterPortfolioTickerList.index(ticker)
                metrics = self.stockDictionary[ticker].GetCurrentMetrics()
                dbMetrics = self.stockDictionary[ticker].GetDatabaseMetrics()
                if metrics is not None and dbMetrics is not None:
                    for column,dataPoint in enumerate(metrics+dbMetrics):
                        # INFO("Updating {}/{} with {}".format(row, column, dataPoint))
                        if dataPoint is not None:
                            widgetItem = self.tableWidget.item(row, column)
                            widgetItem.setText("{:.2f}".format(dataPoint))
                            self.repaint(self.tableWidget.visualItemRect(widgetItem))

    def InitializePortfolioTable(self):
        self.tableWidget = qws.QTableWidget()
        self.tableWidget.setRowCount(len(self.masterPortfolioTickerList))
        self.tableWidget.setColumnCount(len(PORTFOLIO_YFINANCE_COLUMNS)+len(PORTFOLIO_DB_COLUMNS))
        self.tableWidget.setHorizontalHeaderLabels(PORTFOLIO_YFINANCE_COLUMNS+PORTFOLIO_DB_COLUMNS)
        self.tableWidget.setVerticalHeaderLabels(self.masterPortfolioTickerList)
        self.tableWidget.setSizeAdjustPolicy(qws.QAbstractScrollArea.AdjustToContents)
        for sTicker in self.masterPortfolioTickerList:
            rowIndex = self.masterPortfolioTickerList.index(sTicker)
            for columnIndex,key in enumerate(PORTFOLIO_YFINANCE_COLUMNS+PORTFOLIO_DB_COLUMNS):
                self.tableWidget.setItem(rowIndex, columnIndex, qws.QTableWidgetItem(""))

            self.tableWidget.move(0,0)
def main():
    app = qws.QApplication(sys.argv)
    window = StockMonitor()
    window.show()
    app.exec_()



if __name__ == '__main__':
    main()