# Description 

This is a helper role that deploy a python server for github webhook

# Configuration

The following parameter have to be added

```yaml
github_webhook_service_user:
github_webhook_dest_path:
github_webhook_secret:
github_webhook_ssh_key:
github_webhook_repo_url:
github_webhook_repo_branch:
```

`github_webhook_dest_path` correspond to the base path where the repository will be cloned. The name of the repo owner and the repo name will be added to the path.


The `github_webhook_secret` is generated when configuring the webhook in the repository.

The public key associated to `github_webhook_ssh_key` has to be added as a Deploy key in the repository setting.

The user `github_webhook_service_user` can be added to additional group by overriding the list `github_webhook_user_additional_groups`.
