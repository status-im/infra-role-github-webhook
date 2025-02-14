# Source: https://github.com/bloomberg/python-github-webhook
# License: Apache 2.0
# Modification: Changed `request.data` to `request.get_data()` in `_get_digest()`.
# Issue: https://github.com/bloomberg/python-github-webhook/issues/29

import collections
import hashlib
import hmac
import logging
import json
import six
import requests
import aiohttp
import asyncio
from flask import abort, request


class Webhook(object):
    """
    Construct a webhook on the given :code:app.

    :param app: Flask app that will host the webhook
    :param endpoint: the endpoint for the registered URL rule
    :param secret: Optional secret, used to authenticate the hook comes from Github
    :param broadcast_instances: Optional list of other instances where the webhook request should be sent to
    """

    def __init__(self, app=None, endpoint="/postreceive", secret=None, broadcast_instances=[]):
        self.app = app
        self.secret = secret
        self.endpoint = endpoint
        self.broadcast_instances = broadcast_instances
        self._logger = app.logger if app else logging.getLogger("webhook") 
        if app is not None:
            self.init_app(app, endpoint, secret)

    def init_app(self, app, endpoint="/postreceive", secret=None):
        self._hooks = collections.defaultdict(list)
        if secret is not None:
            self.secret = secret
        app.add_url_rule(rule=endpoint, endpoint=endpoint, view_func=self._post_receive, methods=["POST"])

    @property
    def secret(self):
        return self._secret

    @secret.setter
    def secret(self, secret):
        if secret is not None and not isinstance(secret, six.binary_type):
            secret = secret.encode("utf-8")
        self._secret = secret

    def hook(self, event_type="push"):
        """
        Registers a function as a hook. Multiple hooks can be registered for a given type, but the
        order in which they are invoke is unspecified.

        :param event_type: The event type this hook will be invoked for.
        """

        def decorator(func):
            self._hooks[event_type].append(func)
            return func

        return decorator

    def _get_digest(self):
        """Return message digest if a secret key was provided"""

        return hmac.new(self._secret, request.get_data(), hashlib.sha1).hexdigest() if self._secret else None

    async def _post_receive(self):
        """Callback from Flask for direct webhook request"""

        if self.broadcast_instances and 'X-Forwarded-By' not in request.headers:
            await self._forward_to_instances()
        else:
            self._process_request()
        return "", 204


    def _process_request(self):
        """Process the webhook request and execute local hooks"""

        digest = self._get_digest()

        if digest is not None:
            sig_parts = self._get_header("X-Hub-Signature").split("=", 1)
            if not isinstance(digest, six.text_type):
                digest = six.text_type(digest)

            if len(sig_parts) < 2 or sig_parts[0] != "sha1" or not hmac.compare_digest(sig_parts[1], digest):
                self._logger.error(f"Invalid signature {sig_parts}!")
                abort(400, "Invalid signature")

        event_type = self._get_header("X-Github-Event")
        content_type = self._get_header("content-type")
        data = (
            json.loads(request.form.to_dict(flat=True)["payload"])
            if content_type == "application/x-www-form-urlencoded"
            else request.get_json()
        )

        if data is None:
            self._logger.error(f"Request body must contain json!")
            abort(400, "Request body must contain json")

        self._logger.info("%s (%s)", _format_event(event_type, data), self._get_header("X-Github-Delivery"))

        for hook in self._hooks.get(event_type, []):
            hook(data)

    async def _forward_to_instances(self):
        """Forward the request to all instances in the broadcast_instances list asynchronously"""

        async with aiohttp.ClientSession() as session:
            tasks = []
            for instance in self.broadcast_instances:
                task = self._forward_request(session, instance)
                tasks.append(task)
            await asyncio.gather(*tasks)

    async def _forward_request(self, session, instance):
        """Forward the request to a single instance asynchronously"""

        try:
            async with session.request(
                method=request.method,
                url=f"http://{instance}/{self.endpoint}",
                headers={
                    **{k: v for k, v in request.headers.items() if k.lower() != 'host'},
                    "X-Forwarded-By": "webhook-server"
                },
                data=request.get_data(),
                allow_redirects=False,
            ) as response:
                if response.status != 204:
                    self._logger.error(f"Failed to forward request to {instance}. Status Code: {response.status}")
        except aiohttp.ClientError as e:
            self._logger.error(f"Error forwarding request to {instance}: {e}")

    def _get_header(self, key):
        """Return message header"""

        try:
            return request.headers[key]
        except KeyError:
            self._logger.error(f"Missing header {key}")
            abort(400, "Missing header: " + key)


EVENT_DESCRIPTIONS = {
    "commit_comment": "{comment[user][login]} commented on " "{comment[commit_id]} in {repository[full_name]}",
    "create": "{sender[login]} created {ref_type} ({ref}) in " "{repository[full_name]}",
    "delete": "{sender[login]} deleted {ref_type} ({ref}) in " "{repository[full_name]}",
    "deployment": "{sender[login]} deployed {deployment[ref]} to "
    "{deployment[environment]} in {repository[full_name]}",
    "deployment_status": "deployment of {deployement[ref]} to "
    "{deployment[environment]} "
    "{deployment_status[state]} in "
    "{repository[full_name]}",
    "fork": "{forkee[owner][login]} forked {forkee[name]}",
    "gollum": "{sender[login]} edited wiki pages in {repository[full_name]}",
    "issue_comment": "{sender[login]} commented on issue #{issue[number]} " "in {repository[full_name]}",
    "issues": "{sender[login]} {action} issue #{issue[number]} in " "{repository[full_name]}",
    "member": "{sender[login]} {action} member {member[login]} in " "{repository[full_name]}",
    "membership": "{sender[login]} {action} member {member[login]} to team " "{team[name]} in {repository[full_name]}",
    "page_build": "{sender[login]} built pages in {repository[full_name]}",
    "ping": "ping from {sender[login]}",
    "public": "{sender[login]} publicized {repository[full_name]}",
    "pull_request": "{sender[login]} {action} pull #{pull_request[number]} in " "{repository[full_name]}",
    "pull_request_review": "{sender[login]} {action} {review[state]} "
    "review on pull #{pull_request[number]} in "
    "{repository[full_name]}",
    "pull_request_review_comment": "{comment[user][login]} {action} comment "
    "on pull #{pull_request[number]} in "
    "{repository[full_name]}",
    "push": "{pusher[name]} pushed {ref} in {repository[full_name]}",
    "release": "{release[author][login]} {action} {release[tag_name]} in " "{repository[full_name]}",
    "repository": "{sender[login]} {action} repository " "{repository[full_name]}",
    "status": "{sender[login]} set {sha} status to {state} in " "{repository[full_name]}",
    "team_add": "{sender[login]} added repository {repository[full_name]} to " "team {team[name]}",
    "watch": "{sender[login]} {action} watch in repository " "{repository[full_name]}",
}


def _format_event(event_type, data):
    try:
        return EVENT_DESCRIPTIONS[event_type].format(**data)
    except KeyError:
        return event_type


# -----------------------------------------------------------------------------
# Copyright 2015 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ----------------------------- END-OF-FILE -----------------------------------
