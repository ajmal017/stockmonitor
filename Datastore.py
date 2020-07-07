#!/usr/bin/env python3

import sqlite3 as sql

BUY_TRANSACTION = "BUY"
SELL_TRANSACTION = "SELL"

class Datastore(object):
	def __init__(self, dbpath = "./stockdata.db"):
		self.path = dbpath
		self.connection = sql.connect(self.path)
		self.cursor = self.connection.cursor()
		self._createTables()

	def Reset(self):
		stmt = "DROP TABLE IF EXISTS {}".format("Positions")
		self.cursor.execute(stmt)
		stmt = "DROP TABLE IF EXISTS {}".format("Trades")
		self.cursor.execute(stmt)
		self.connection.commit()
		self._createTables()

	def _createTables(self):
		stmt = "CREATE TABLE IF NOT EXISTS Positions(ticker TEXT PRIMARY KEY, volume INTEGER, averagePrice REAL)"
		self.cursor.execute(stmt)
		stmt = "CREATE TABLE IF NOT EXISTS Trades(id INTEGER PRIMARY KEY, ticker TEXT, ttype TEXT, volume INTEGER, price REAL, date TEXT)"
		self.cursor.execute(stmt)

	# -- Action Functions --
	def LogTrade(self, ticker, transaction, volume, price, date):
		newPrice = None
		newVolume = None
		stmt = "INSERT INTO Trades(ticker, ttype, volume, price, date) VALUES(?, ?,?,?,?)"
		self.cursor.execute(stmt, (ticker, transaction, volume, price, date))

		# Trade is logged, now calculate our current position
		curPosition = self.GetPosition(ticker)
		if len(curPosition) == 0:
			curPosition = [0,0,0]
		else:
			curPosition = curPosition[0]
		oldVolume = curPosition[1]
		oldPrice = curPosition[2]

		if transaction == BUY_TRANSACTION:
			newVolume = oldVolume + volume
			newPrice = ((oldVolume*oldPrice) + (volume*price))/newVolume
		else:
			newVolume = oldVolume - volume
			newPrice = newVolume*oldPrice
			if newVolume < 0:
				raise Exception("Error: Volume is now negative! Assigning to 0, please check your database")
				newVolume = 0

		stmt = "REPLACE INTO Positions VALUES(?,?,?)"
		self.cursor.execute(stmt, (ticker, newVolume, newPrice))
		self.connection.commit()

	# -- Get Functions -- 
	def GetAllTrades(self):
		stmt = "SELECT * FROM Trades"
		return self.cursor.execute(stmt).fetchall()

	def GetTradesByTicker(self, ticker):
		stmt = "SELECT * FROM Trades WHERE ticker = ?"
		trades = self.cursor.execute(stmt,(ticker,)).fetchall()
		return trades

	def GetPosition(self, ticker):
		stmt = "SELECT * FROM Positions where ticker = ?"
		position = self.cursor.execute(stmt, (ticker,)).fetchall()
		if len(position)>0:
			position = position[0]
		return position

	def GetAllPositions(self):
		stmt = "SELECT * FROM Positions"
		positions = self.cursor.execute(stmt)
		return positions.fetchall()

if __name__ == "__main__":
	db = Datastore(dbpath = "./debug.db")
	db.Reset()
	db.LogTrade('DAL',BUY_TRANSACTION,3,33.23,'2020-03-28')
	trades = db.GetTradesByTicker('DAL')
	positions = db.GetAllPositions()
	print(trades)
	print(positions)
	print("="*10)
	db.LogTrade('DAL',SELL_TRANSACTION,2,11,'2020-03-29')
	positions = db.GetPosition('DAL')
	print(positions)
	print("="*10)
	db.LogTrade('DAL',BUY_TRANSACTION,1,66.23,'2020-03-30')
	positions = db.GetAllPositions()
	trades = db.GetAllTrades()
	print(trades)
	print(positions)