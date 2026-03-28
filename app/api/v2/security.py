import functools
import inspect
import json
import re
import types

from aiohttp import web

READ_ONLY_SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
READ_ONLY_SAFE_API_REST_POST_INDEXES = frozenset({
    'agent_configuration',
    'contact',
    'exfil_files',
    'link',
    'operation_report',
    'result'
})
READ_ONLY_SAFE_PATH_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r'^/logout$',
    r'^/api/v2/operations/[^/]+/report$',
    r'^/api/v2/operations/[^/]+/event-logs$',
    r'^/plugin/access/abilities$',
    r'^/plugin/access/executor$',
    r'^/plugin/gameboard/pieces$',
    r'^/plugin/manx/sessions$',
    r'^/plugin/manx/history$',
    r'^/plugin/manx/ability$',
    r'^/plugin/debrief/report$',
    r'^/plugin/debrief/graph$',
    r'^/plugin/debrief/pdf$',
    r'^/plugin/debrief/json$',
    r'^/plugin/compass/layer$'
))


def is_handler_authentication_exempt(handler):
    """Return True if the endpoint handler is authentication exempt."""
    try:
        if hasattr(handler, '__caldera_unauthenticated__'):
            is_unauthenticated = handler.__caldera_unauthenticated__
        else:
            is_unauthenticated = handler.keywords.get('handler').__caldera_unauthenticated__
    except AttributeError:
        is_unauthenticated = False
    return is_unauthenticated


def _wrap_async_method(method: types.MethodType):
    """Wrap the input bound async method in an async function."""
    async def wrapper(*args, **kwargs):
        return await method(*args, **kwargs)
    return functools.wraps(method)(wrapper)


def _wrap_sync_method(method: types.MethodType):
    """Wrap the input bound method in an async function."""
    def wrapper(*args, **kwargs):
        return method(*args, **kwargs)
    return functools.wraps(method)(wrapper)


def _wrap_method(method: types.MethodType):
    if inspect.iscoroutinefunction(method):
        return _wrap_async_method(method)
    return _wrap_sync_method(method)


def authentication_exempt(handler):
    """Mark the endpoint handler as not requiring authentication.

    Note:
        This only applies when the authentication_required_middleware is
        being used.
    """
    # Can't set attributes directly on a bound method so we need to
    # wrap it in a function that we can mark it as unauthenticated
    if inspect.ismethod(handler):
        handler = _wrap_method(handler)
    handler.__caldera_unauthenticated__ = True
    return handler


def authentication_required_middleware_factory(auth_svc):
    """Enforce authentication on every endpoint within an web application.

    Note:
        Any endpoint handler can opt-out of authentication using the
        @authentication_exempt decorator.
    """
    @web.middleware
    async def authentication_required_middleware(request, handler):
        if is_handler_authentication_exempt(handler):
            return await handler(request)
        if not await auth_svc.is_request_authenticated(request):
            raise web.HTTPUnauthorized()
        return await handler(request)
    return authentication_required_middleware


async def _is_read_only_safe_request(request):
    """Return True when a read-only session should be allowed to perform the request.

    Some legacy and plugin read/report workflows still use POST even though they do
    not mutate server state, so this check must be more precise than a method test.
    """
    if request.method in READ_ONLY_SAFE_METHODS:
        return True

    if any(pattern.match(request.path) for pattern in READ_ONLY_SAFE_PATH_PATTERNS):
        return True

    if request.method == 'POST' and request.path == '/api/rest':
        try:
            request_body = json.loads((await request.read()) or b'{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        return request_body.get('index') in READ_ONLY_SAFE_API_REST_POST_INDEXES

    return False


def read_only_middleware_factory(auth_svc):
    """Block state-changing GUI requests for read-only sessions.

    The check is session-aware, so agent traffic and API-key-based automation keep
    their current behavior. Safe read/report endpoints that still use POST are
    allowlisted explicitly.
    """
    @web.middleware
    async def read_only_middleware(request, handler):
        if await _is_read_only_safe_request(request):
            return await handler(request)

        if not (await auth_svc.request_has_valid_user_session(request) or auth_svc.request_has_valid_api_key(request)):
            return await handler(request)

        if await auth_svc.request_can_write(request):
            return await handler(request)

        raise web.HTTPForbidden(reason='Read-only users cannot modify Caldera state.')

    return read_only_middleware


@web.middleware
async def pass_option_middleware(request, handler):
    """Allow all 'OPTIONS' request to the server to return 200
    This mitigates CORS issues while developing the UI.
    """
    if request.method == 'OPTIONS':
        raise web.HTTPOk()
    return await handler(request)
