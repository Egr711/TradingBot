import ibapi

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.contract import ContractDetails
from ibapi.order import Order
from ibapi.scanner import ScannerSubscription
from ibapi.tag_value import TagValue

import threading
import time
import math

buying = True;


class IBapi(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)
        self.data = []
        self.stocks = []
        self.positions = []
        self.doneScanner = False
        self.donePositions = False
        self.currentPrice = 0

    # cancelling order
    def error(self, reqId, errorCode, errorString):
        if errorCode == 202:
            print('order canceled')

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType == 4:
            # print('The current price is: ', price)
            self.currentPrice = price

    def historicalData(self, reqId, bar):
        #print(f'Time: {bar.date} Close: {bar.close}')
        self.data.append([bar.date, bar.close])

    def historicalDataEnd(self, reqId, start, end):
        super().historicalDataEnd(reqId, start, end)
        #print("HistoricalDataEnd. ReqId:", reqId, "from", start, "to", end)

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextorderId = orderId
        print('The next valid order id is: ', self.nextorderId)

    def orderStatus(self, orderId, status, filled, remaining, avgFullPrice, permId, parentId, lastFillPrice, clientId,
                    whyHeld, mktCapPrice):
        '''
        print('orderStatus - orderid:', orderId, 'status:', status, 'filled', filled, 'remaining', remaining,
              'lastFillPrice', lastFillPrice)'''

    def openOrder(self, orderId, contract, order, orderState):
        '''
        print('openOrder id:', orderId, contract.symbol, contract.secType, '@', contract.exchange, ':', order.action,
              order.orderType, order.totalQuantity, orderState.status)'''

    def execDetails(self, reqId, contract, execution):
        '''
        print('Order Executed: ', reqId, contract.symbol, contract.secType, contract.currency, execution.execId,
              execution.orderId, execution.shares, execution.lastLiquidity)'''

    def scannerData(self, reqId: int, rank: int, contractDetails: ContractDetails, distance: str, benchmark: str,
                    projection: str, legsStr: str):
        super().scannerData(reqId, rank, contractDetails, distance, benchmark, projection, legsStr)
        print("ScannerData. ReqId:", reqId, "Rank:", rank, "Symbol:", contractDetails.contract.symbol,
              "SecType:", contractDetails.contract.secType,
              "Currency:", contractDetails.contract.currency)
        self.stocks.append(contractDetails.contract)

    def scannerDataEnd(self, reqId: int):
        super().scannerDataEnd(reqId)
        print("ScannerDataEnd. ReqId:", reqId)
        self.cancelScannerSubscription(reqId)
        self.doneScanner = True

    def position(self, account: str, contract: Contract, position: float,
                 avgCost: float):
        super().position(account, contract, position, avgCost)
        if position > 0:
            self.positions.append(contract)
            print("Position.",  "Symbol:", contract.symbol,
                  "Position:", position, "Avg cost:", avgCost)

    def positionEnd(self):
        super().positionEnd()
        print("PositionEnd")
        self.cancelPositions()
        self.donePositions = True


def run_loop():
    app.run()


def Create_Contract(symbol, secType='STK', exchange='SMART', currency='USD'):
    # custom function to create stock contract
    contract = Contract()
    contract.symbol = symbol
    contract.secType = secType
    contract.exchange = exchange
    contract.currency = currency
    return contract


def Create_Order(action, quantity=10):
    order = Order()
    order.action = action
    order.totalQuantity = quantity
    order.orderType = 'MKT'
    # order.lmtPrice = '1.10'
    order.orderId = app.nextorderId
    app.nextorderId += 1
    return order


def getBollingerBands():
    mean = 0
    for i in app.data[-20:]:
        mean += float(i[1])
    mean = mean / 20

    standardDeviation = 0
    for i in app.data[-20:]:
        standardDeviation = standardDeviation + (float(i[1]) - mean) * (float(i[1]) - mean)
    standardDeviation = math.sqrt(standardDeviation / 20)
    upperBand = mean + 2 * standardDeviation
    lowerBand = mean - 2 * standardDeviation
    return lowerBand, upperBand


app = IBapi()
app.connect('127.0.0.1', 7497, 500)

app.nextorderId = None
requestID = 0

# Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

# Check if the API is connected via orderid
while True:
    if isinstance(app.nextorderId, int):
        print('connected')
        break
    else:
        print('waiting for connection')
        time.sleep(1)


print("App is connected: " + str(app.isConnected()))

topLosers = ScannerSubscription()
topLosers.instrument = "STK"
topLosers.locationCode = "STK.US.MAJOR"
topLosers.scanCode = "TOP_PERC_LOSE"
topLosers.aboveVolume = "500000"
topLosers.abovePrice = "10"

tagValues = [TagValue("changePercAbove", "-30")]
tagValues.append(TagValue("changePercBelow", "-3"))

scanner = app.reqScannerSubscription(requestID, topLosers, [], scannerSubscriptionFilterOptions=tagValues)
requestID += 1

stocksUnder = []

while buying:
    if app.doneScanner:
        for contract in app.stocks:
            app.reqHistoricalData(requestID, contract, '', '20 D', '1 day', 'TRADES', 1, 2, False, [])
            requestID += 1

            while True:
                if len(app.data) == 20:

                    bands = getBollingerBands()
                    threshold = .15 * (bands[1] - bands[0])
                    app.reqMktData(requestID, contract, "", False, False, [])

                    while app.currentPrice == 0:
                        time.sleep(1)

                    if app.currentPrice < (round(bands[0], 2) - threshold):
                        stocksUnder.append(contract)
                        print("SYMBOL: ", contract.symbol, "LowerBand: ", round(bands[0], 2), "Upper Band: ",
                              round(bands[1], 2), "CurrentPrice: ", app.currentPrice)

                        order = Create_Order("BUY")
                        app.placeOrder(order.orderId, contract, order)
                        time.sleep(1)

                    requestID += 1

                    app.data = []
                    app.currentPrice = 0
                    break
        buying = False
        break

    else:
        print("Waiting for scanner to finish")
        time.sleep(2)

print("Finished buying")

app.reqPositions()

while not buying:
    if app.donePositions:
        while True:
            for position in app.positions:
                contract = Create_Contract(position.symbol) # Using position for historical data wasnt working so i had to do this
                app.reqHistoricalData(requestID, contract, '', '20 D', '1 day', 'TRADES', 1, 2, False, [])
                requestID += 1

                while len(app.data) != 20:
                    time.sleep(1)

                app.reqMktData(requestID, contract, "", False, False, [])
                bands = getBollingerBands()

                while app.currentPrice == 0:
                    time.sleep(1)

                print(contract.symbol, " ", app.currentPrice)
                if app.currentPrice >= round(bands[1], 2):
                    print("==========SELLING ", contract.symbol, " =====================")
                    order = Create_Order("SELL")
                    app.placeOrder(order.orderId, contract, order)

                app.data = []
                app.currentPrice = 0
            app.positions = []
            app.reqPositions()
            print("--------------Waiting for 30 seconds----------------------")
            time.sleep(30)

    else:
        print("Waiting for positions")
        time.sleep(2)
