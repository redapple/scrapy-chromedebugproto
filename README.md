# scrapy-chromedebugproto

Example of how to integrate Scrapy with [Chrome Debugging Protocol](https://chromedevtools.github.io/debugger-protocol-viewer/)

**WARNING: highly toxic code!! Not production-ready, not at all!!**
You've been warned.

## Getting started

### Get a recent Chrome, with headless mode if you can

Run with for example

```
$ google-chrome-unstable --disable-gpu --headless --remote-debugging-port=9223
```

### Install Python dependencies

- scrapy
- treq
- twisted
- autobahn

### Add the dowloader middleware

```
DOWNLOADER_MIDDLEWARES = {
    'middleware.HeadlesschromeDownloaderMiddleware': 543,
}
```

## Todo

- Handle non-HTTP 200 responses
- switch debug logs on/off
- configurable debugger URL
- a proper state machine
- make a Python package out of it
- check how load and requests concurrency is handled
- add tests
- ...
