#!/usr/bin/env python3
import string
import random

from gornilo import Checker, CheckRequest, PutRequest, GetRequest, Verdict
from api import Api
import proto.office_pb2 as pb
import re
from errs import INVALID_FORMAT_ERR, FAILED_TO_CONNECT

checker = Checker()


def get_random_str(length=10, only_chars=False):
    if only_chars:
        return "".join(random.choices(string.ascii_letters, k=length))
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def create_doc():
    a = get_random_str(length=4, only_chars=True)
    b = get_random_str(length=4, only_chars=True)
    return f"""
vars:
  {a}: 'bio'
  {b}: 'name'
exprs:
  - name: {a}
    expr: "get_info({a})"
  - name: {b}
    expr: "get_info({b})"
---
Hi '{{username}}'!
Name: '{{{b}}}'
Bio: '{{{a}}}'"""


def create_doc_with_flag(flag: str):
    return f"""
vars:
  sercretinfo: '{flag}'
---
Secret info: '{{sercretinfo}}'!!!"""


@checker.define_check
async def check_service(request: CheckRequest) -> Verdict:
    api = Api(f'{request.hostname}:8080')
    # check /docs/test
    name = get_random_str()
    password = get_random_str(30)
    bio = get_random_str(30)
    req = pb.RegisterRequest()
    req.name = name
    req.password = password
    req.bio = bio
    err = api.register(req)
    if err != None:
        return verdict_from_api_err(err)
    doc = create_doc()
    req = pb.TestDocRequest()
    req.content = doc
    r, err = api.test_doc(req)
    if err != None:
        return verdict_from_api_err(err)
    try:
        executed = r["executed"]
    except:
        return Verdict.MUMBLE(err)
    di, err = DocInfo.parse(executed)
    if err != None:
        return Verdict.MUMBLE(err)
    if di.name != di.username:
        return Verdict.MUMBLE(INVALID_FORMAT_ERR)
    if di.bio != bio:
        return Verdict.MUMBLE("invalid flag")

    return Verdict.OK()


@checker.define_put(vuln_num=1, vuln_rate=2)
async def put(request: PutRequest) -> Verdict:
    api = Api(f'{request.hostname}:8080')
    name = get_random_str()
    password = get_random_str(30)

    req = pb.RegisterRequest()
    req.name = name
    req.password = password
    req.bio = request.flag
    err = api.register(req)
    if err != None:
        return verdict_from_api_err(err)
    verdict = check_users_pagination(api, "", name)
    if verdict != None:
        return verdict
    d = create_doc()
    req = pb.CreateDocumentRequest()
    req.name = name
    req.doc = d
    r, err = api.create_doc(req)
    if err != None:
        return verdict_from_api_err(err)
    try:
        doc_id = r.id
    except:
        return Verdict.MUMBLE(INVALID_FORMAT_ERR)
    verdict = check_docs_pagination(api, doc_id, name)
    if verdict != None:
        return verdict
    return Verdict.OK(f"{name}:{password}:{doc_id}:{r.token}")


def check_users_pagination(api: Api, user_id, username):
    offset = 0
    while True:
        req = pb.ListRequest()
        req.offset = offset
        req.limit = 3000
        r, err = api.list_users(req)
        if err != None:
            return verdict_from_api_err(err)
        if not hasattr(r, 'usernames'):
            return Verdict.MUMBLE("invalid users listing")
        for u in r.usernames:
            if username == u:
                return None
        if len(r.usernames) < 3000:
            return Verdict.MUMBLE("invalid users listing")
        offset += 3000


def check_docs_pagination(api: Api, doc_id, doc_name):
    offset = 0
    while True:
        req = pb.ListDocumentsRequest()
        req.offset = offset
        req.limit = 3000
        r, err = api.list_doc(req)
        if err != None:
            return verdict_from_api_err(err)
        if not hasattr(r, 'docs'):
            return Verdict.MUMBLE("invalid docs listing")
        for d in r.docs:
            if doc_name == d.name and doc_id == d.id:
                print(f"found doc with id {doc_id}")
                return None
        if len(r.docs) < 3000:
            return Verdict.MUMBLE("invalid docs listing")
        offset += 3000


@checker.define_put(vuln_num=2, vuln_rate=1)
async def put_2(request: PutRequest) -> Verdict:
    api = Api(f'{request.hostname}:8080')
    name = get_random_str()
    password = get_random_str(30)
    req = pb.RegisterRequest()
    req.name = name
    req.password = password
    req.bio = request.flag
    err = api.register(req)
    if err != None:
        return verdict_from_api_err(err)
    check_users_pagination(api, "", name)
    req = pb.CreateDocumentRequest()
    req.name = name
    req.doc = create_doc_with_flag(request.flag)
    r, err = api.create_doc(req)
    if err != None:
        return verdict_from_api_err(err)
    try:
        doc_id = r.id
    except:
        return Verdict.MUMBLE(INVALID_FORMAT_ERR)
    verdict = check_docs_pagination(api, doc_id, name)
    if verdict != None:
        return verdict
    return Verdict.OK(f"{name}:{password}:{doc_id}:{r.token}")


@checker.define_get(vuln_num=1)
async def get(request: GetRequest) -> Verdict:
    api = Api(f'{request.hostname}:8080')
    name, password, id, token = request.flag_id.strip().split(":")
    req = pb.LoginRequest()
    req.name = name
    req.password = password
    err = api.login(req)
    if err != None:
        return verdict_from_api_err(err)
    req = pb.ExecuteRequest()
    req.doc_id = int(id)
    req.token = token
    r, err = api.execute_doc(req)
    if err != None:
        return verdict_from_api_err(err)
    try:
        executed = r["executed"]
    except:
        return Verdict.MUMBLE(err)
    di, err = DocInfo.parse(executed)
    if err != None:
        return Verdict.MUMBLE(err)
    if di.name != di.username:
        return Verdict.MUMBLE(INVALID_FORMAT_ERR)
    if di.bio != request.flag:
        return Verdict.MUMBLE("invalid flag")
    return Verdict.OK()


@checker.define_get(vuln_num=2)
async def get_2(request: GetRequest) -> Verdict:
    api = Api(f'{request.hostname}:8080')
    name, password, id, token = request.flag_id.strip().split(":")
    req = pb.LoginRequest()
    req.name = name
    req.password = password
    err = api.login(req)
    if err != None:
        return verdict_from_api_err(err)
    req = pb.ExecuteRequest()
    req.doc_id = int(id)
    req.token = token
    r, err = api.execute_doc(req)
    if err != None:
        return verdict_from_api_err(err)
    try:
        executed = r["executed"]
    except:
        return Verdict.MUMBLE(INVALID_FORMAT_ERR)
    di, err = DocInfo.parse_static(executed)
    if err != None:
        return Verdict.MUMBLE(err)
    if di.secret_info != request.flag:
        return Verdict.MUMBLE("invalid flag")
    return Verdict.OK()


class DocInfo:
    USERNAME_RE = "Hi '(.*)'!"
    NAME_RE = "Name: '(.*)'"
    BIO_RE = "Bio: '(.*)'"
    SECRET_RE = "Secret info: '(.*)'!!!"

    def __init__(self, username: str, name: str, bio: str, secret_info: str):
        self.username: str = username
        self.name: str = name
        self.bio: str = bio
        self.secret_info: str = secret_info

    @staticmethod
    def parse(content: str) -> (object, str):
        splitted = content.split('\n')
        if len(splitted) != 3:
            print(f"invalid lines count was: {len(splitted)} want: 3")
            return None, INVALID_FORMAT_ERR
        try:
            m = re.match(DocInfo.USERNAME_RE, splitted[0])
            username = m.group(1)
            m = re.match(DocInfo.NAME_RE, splitted[1])
            name = m.group(1)
            m = re.search(DocInfo.BIO_RE, splitted[2])
            bio = m.group(1)
        except Exception as e:
            print(e)
            return None, INVALID_FORMAT_ERR
        return DocInfo(username, name, bio, ""), None

    @staticmethod
    def parse_static(content: str) -> (object, str):
        splitted = content.split('\n')
        if len(splitted) != 1:
            print(f"invalid lines count was: {len(splitted)} want: 1")
            return None, INVALID_FORMAT_ERR
        try:
            m = re.match(DocInfo.SECRET_RE, splitted[0])
            secret_info = m.group(1)
        except Exception as e:
            print(e)
            return None, INVALID_FORMAT_ERR
        return DocInfo("", "", "", secret_info), None


def verdict_from_api_err(err: str) -> Verdict:
    if err == "failed to connect":
        return Verdict.DOWN(err)
    else:
        return Verdict.MUMBLE(err)


if __name__ == '__main__':
    checker.run()
