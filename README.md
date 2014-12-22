Helper for migrating projects to GitHub
=======================================

This is a GAE app for collecting user access tokens and emails needed to import
issues and comments onto GitHub preserving original message authors and
timestamps.

Configuring and running
-----------------------
First of all, you need to pick a project ID - a unique name that eventually
will become a third level domain name on \*.appspot.com hosting.
We'll use **my-project-github-migrator** as an example ID.

Clone the repository (optionally, fork it before cloning) and create `config.py`
file; use `config-template.py` as a starting point:
```
$ git clone git@github.com:abusalimov/github-migrator-gae.git
$ cd github-migrator-gae
$ cp config-template.py config.py
```

Open `config.py` for editing and first of all set proper values to `PROJECT`
dict; these values are used to render the main web-page and only affect
a content your users will see on the web-page.
Then enter your email as `ADMIN_EMAIL` and assign a random string to
`SECRET` variable. The rest settings are covered below.

Open `app.yaml` and change the value of the `application:` setting to
your application ID: **my-project-github-migrator**.

### Google App Engine project
Log into [Google Developer Console](https://console.developers.google.com/project)
and create a new project. Choose a name and enter the project ID here.

Open the project, go to _Credentials_ under _APIs & auth_ section,
and _Create new Client ID_. Select _Web application_ and proceed
to _Configure consent screen_. Fill in the necessary fields and _Save_,
you'll be brought back to creating Client ID window, where you need to enter
some URIs:

| Field                         | Value
| ----------------------------- | ----------------
| Authorized Javascript Origins | https://**my-project-github-migrator**.appspot.com
| Authorized Redirect URIs      | https://**my-project-github-migrator**.appspot.com/app/login/google

Press _Create client ID_ and you will get the ID and secret that you need
to paste into `GOOGLE_AUTH` dict inside your `config.py`.

### GitHub organization application
First of all, [create](https://github.com/organizations/new) new organization,
if you haven't done it yet. Open your organization settings (you can find them
through your [settings](https://github.com/settings/profile) screen),
go to _Applications_ and _Register new application_. Fill in all necessary fields,
these ones as follows:

| Field                         | Value
| ----------------------------- | ----------------
| Homepage URL                  | https://**my-project-github-migrator**.appspot.com
| Authorization callback URL    | https://**my-project-github-migrator**.appspot.com/app/login/github

Press _Register application_ and you will get the ID and secret that you need
to paste into `GITHUB_AUTH` dict inside your `config.py`.

### Deploy
Setup necessary tools as described [here](https://cloud.google.com/sdk/):
```
$ curl https://sdk.cloud.google.com/ | bash
```
Restart the shell.
```
$ gcloud auth login
$ gcloud components update gae-python
$ appcfg.py --oauth2 -A my-project-github-migrator update github-migrator-gae
```

The application will be available at https://**my-project-github-migrator**.appspot.com
