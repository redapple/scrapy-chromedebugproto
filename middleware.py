from collections import defaultdict
from itertools import count
import json
from pprint import pformat

import scrapy
import treq
from twisted.internet.defer import inlineCallbacks, Deferred
from autobahn.twisted.websocket import WebSocketClientFactory, \
    WebSocketClientProtocol, connectWS


class ChromeDebuggingProtocol(WebSocketClientProtocol):
    """Toy websocket protocol for Autobahn to get the HTML for a URL."""

    STATE_INIT = 1
    STATE_PAGE_REQUESTED = 2
    STATE_DOCUMENT_REQUESTED = 3
    STATE_HTML_REQUESTED = 4

    def __init__(self, *args, **kwargs):
        super(ChromeDebuggingProtocol, self).__init__(*args, **kwargs)
        self.pstate = self.STATE_INIT
        self.curr_id = None
        self.page_frameid = None

    def dataReceived(self, data):
        #print("dataReceived(%r)" % data)
        super(ChromeDebuggingProtocol, self).dataReceived(data)

    def onConnect(self, response):
        print("Server connected: {0}".format(response.peer))
        self.reqidit = self.factory.reqidit

    def onOpen(self):
        print("WebSocket connection open.")

        self.pageEnable()
        self.networkEnable()
        self.domEnable()
        self.logEnable()
        self.network_requests = defaultdict(dict)

        self.curr_id = self.pageNavigate(self.factory.navigate_to)
        self.pstate = self.STATE_PAGE_REQUESTED

    def onMessage(self, payload, isBinary):
        if isBinary:
            print("<------\nBinary message received: {0} bytes".format(len(payload)))
        else:
            data = json.loads(payload.decode('utf8'))
            print("<------\nText message received:\n{0}".format(pformat(data)))

            method = data.get('method')
            params = data.get('params')
            message_id = data.get('id')
            result = data.get('result')

            if message_id is not None and result is not None:
                if message_id == self.curr_id:

                    if self.pstate == self.STATE_PAGE_REQUESTED:
                        if self.page_frameid is None and result.get('frameId'):
                            self.page_frameid = result.get('frameId')

                    elif self.pstate == self.STATE_DOCUMENT_REQUESTED:

                        node_id = data['result']['root']['nodeId']
                        self.pstate = self.STATE_HTML_REQUESTED
                        self.curr_id = self.domGetOuterHtml(node_id)

                    elif self.pstate == self.STATE_HTML_REQUESTED:
                        frameId = self.page_frameid
                        request = self.network_requests[frameId]['request']
                        response = self.network_requests[frameId]['response']

                        rsp = scrapy.http.TextResponse(url=response['url'],
                            status=response['status'],
                            headers=response['headers'],
                            body=result['outerHTML'].encode('utf-8'))

                        self.factory.on_navigate.callback(rsp)

            elif method is not None:
                if method == 'Page.frameNavigated':
                    if self.pstate == self.STATE_PAGE_REQUESTED:
                        if self.page_frameid ==  params['frame']['id']:
                            self.curr_id = self.domGetDocument()
                            self.pstate = self.STATE_DOCUMENT_REQUESTED

                elif method == 'Network.requestWillBeSent':
                    reqId, frameId = params['requestId'], params['frameId']
                    if reqId == frameId:
                        self.network_requests[frameId]['request'] = params['request']
                        self.page_frameid = frameId

                elif method == 'Network.responseReceived':
                    reqId, frameId = params['requestId'], params['frameId']
                    if reqId == frameId:
                        self.network_requests[frameId]['response'] = params['response']

                #elif method == 'Network.loadingFinished':
                    #reqId = params['requestId']
                    #if self.pstate == self.STATE_PAGE_REQUESTED:
                        #for fid in self.network_requests:
                            #if fid == reqId:
                                #self.curr_id = self.domGetDocument()
                                #self.pstate = self.STATE_DOCUMENT_REQUESTED

                elif method == 'DOM.documentUpdated':
                    if self.pstate == self.STATE_DOCUMENT_REQUESTED:
                        self.curr_id = self.domGetDocument()


    def onClose(self, wasClean, code, reason):
        print("WebSocket connection closed: {0}".format(reason))

    def sendAction(self, data):
        if 'id' not in data:
            data['id'] = next(self.reqidit)
        print("------>\nMessage send:\n{0}".format(pformat(data)))
        self.sendMessage(json.dumps(data).encode('utf-8'))
        return data['id']

    def pageEnable(self):
        self.sendAction({
            'method': 'Page.enable',
        })

    def networkEnable(self):
        self.sendAction({
            'method': 'Network.enable',
        })

    def domEnable(self):
        self.sendAction({
            'method': 'DOM.enable',
        })

    def logEnable(self):
        self.sendAction({
            'method': 'Log.enable',
        })

    def pageNavigate(self, url):
        return self.sendAction({
            'method': 'Page.navigate',
            'params': {'url': url}
        })

    def domGetDocument(self):
        return self.sendAction({
            'method': 'DOM.getDocument',
        })

    def domGetOuterHtml(self, node_id):
        return self.sendAction({
            'method': 'DOM.getOuterHTML',
            'params': {'nodeId': node_id}
        })


class ChromeDebuggingClientFactory(WebSocketClientFactory):

    protocol = ChromeDebuggingProtocol

    def __init__(self,
                 url=None,
                 origin=None,
                 protocols=None,
                 useragent=None,
                 headers=None,
                 proxy=None,
                 navigate_to=None,
                 on_navigate=None):
        super(ChromeDebuggingClientFactory, self).__init__(
            url=url,
            origin=origin,
            protocols=protocols,
            useragent=useragent,
            headers=headers,
            proxy=proxy)

        self.navigate_to = navigate_to
        self.on_navigate = on_navigate
        self.reqidit = count(1)


class HeadlesschromeDownloaderMiddleware(object):
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.


    @inlineCallbacks
    def process_request(self, request, spider):
        resp = yield treq.post('http://localhost:9223/json/new')
        content = yield resp.json()

        on_page = Deferred()
        factory = ChromeDebuggingClientFactory(url=content['webSocketDebuggerUrl'],
                                               navigate_to=request.url,
                                               on_navigate=on_page)
        connectWS(factory)
        yield on_page
