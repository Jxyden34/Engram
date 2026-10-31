"""Receive, multipart cleanup and bounded file-buffer regressions."""
import asyncio
import io
from unittest.mock import patch
import pytest
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.testclient import TestClient
from starlette.formparsers import SpooledTemporaryFile
from app.request_limits import RequestLimitMiddleware
from app import documents


def toy():
    app=FastAPI()
    app.add_middleware(RequestLimitMiddleware)
    @app.post('/api/v1/documents')
    async def file_route(file:UploadFile=File(...)):
        return {'size':len(await file.read())}
    @app.post('/oauth/register')
    async def json_route(request:Request):
        return await request.json()
    return app


def test_declared_and_streaming_limits_enforce_actual_bytes(monkeypatch):
    monkeypatch.setattr('app.request_limits.request_limit',lambda path:16)
    http=TestClient(toy())
    assert http.post('/oauth/register',content=b'{}').status_code==200
    assert http.post('/oauth/register',content=b'x'*17).status_code==413
    assert http.post('/oauth/register',content=b'x'*17,headers={'Content-Length':'2'}).status_code==413
    assert http.post('/oauth/register',content=b'{}',headers={'Content-Length':'bad'}).status_code==400


def test_chunked_multipart_limit_closes_partial_spool(monkeypatch):
    monkeypatch.setattr('app.request_limits.request_limit',lambda path:1024)
    raw=(b'--bound\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\nContent-Type: text/plain\r\n\r\n'+b'a'*3000+b'\r\n--bound--\r\n')
    chunks=[raw[i:i+256] for i in range(0,len(raw),256)]
    messages=[];files=[];reads=0
    async def receive():
        nonlocal reads
        reads+=1
        body=chunks.pop(0)
        return {'type':'http.request','body':body,'more_body':bool(chunks)}
    async def send(message):messages.append(message)
    def spool(*args,**kwargs):
        file=SpooledTemporaryFile(*args,**kwargs);files.append(file);return file
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST','path':'/api/v1/documents','raw_path':b'/api/v1/documents','query_string':b'','headers':[(b'content-type',b'multipart/form-data; boundary=bound')],'client':('127.0.0.1',1),'server':('localhost',80),'scheme':'http'}
    with patch('starlette.formparsers.SpooledTemporaryFile',spool):asyncio.run(toy()(scope,receive,send))
    assert messages[0]['status']==413 and reads==5
    assert files and all(file.closed for file in files)
    assert chunks,'parser must stop before exhausting the oversized body'


def test_bounded_reads_reject_before_full_buffer_and_keep_ordinary_upload(monkeypatch):
    class File:
        def __init__(self):self.reads=[];self.remaining=100
        async def read(self,size):
            self.reads.append(size);n=min(size,self.remaining);self.remaining-=n;return b'x'*n
    file=File()
    with pytest.raises(HTTPException) as error:asyncio.run(documents.read_limited(file,10))
    assert error.value.status_code==413 and file.remaining==89 and file.reads==[11]
    assert asyncio.run(documents.read_limited(UploadFile(io.BytesIO(b'hello')),5))==b'hello'
    assert asyncio.run(documents.read_limited(UploadFile(io.BytesIO(b'')),5))==b''
