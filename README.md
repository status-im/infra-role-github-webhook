# Description 

This is a helper role that deploy a python server for github webhook

# Configuration

Required configuration:
```yaml
github_webhook_dest_path: '/opt/repo'
github_webhook_secret: 'super-secret-webhook-secret'
github_webhook_repo_url: 'https://github.com/example-org/example-repo'
github_webhook_repo_branch: 'master'
```
Additionally these options can be useful:
```yaml
github_webhook_ssh_key: '-----BEGIN OPENSSH PRIVATE KEY-----\n...'
github_webhook_service_user: 'repouser'
github_webhook_user_additional_groups: ['docker']
github_webhook_service_user_uid: 1500
```
Explanations:

* `github_webhook_dest_path` - Absolute path for repository location.
* `github_webhook_secret` - Used to configure the webhook in GitHub repository.
* `github_webhook_ssh_key` - Optional private SSH key to checkout private repositories.
* `github_webhook_service_user` - Define user to own the repo and run the service.
* `github_wehbook_service_user_groups` - Modify list of groups of service user.
* `github_webhook_service_user_uid` - Change UID of service user to match repo user.
