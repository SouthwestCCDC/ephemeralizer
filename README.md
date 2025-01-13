# Ephemeralizer

## Summary

This is a tool to create sparkling backups in the TALON Cyber League's private cloud.
The idea is to turn stateful instances into ephemeral instances you can set and forget,
then roll the instance at will. Hence, `ephemeralizer`.

It relies on a semi-persistent deployment of minio, which then itself syncs to AWS S3.

It bootstraps a single directory with content pulled from a service-specific location
in a minio S3 bucket, then regularly syncs the content of that directory back to the
bucket as it gets updates in the system.

## pyenv instructions

If you're just installing this tool with pipx, you don't need to mess with the environment.
However, if you want to run it without installing it, `pyenv` is the easiest way. Set up
your `pyenv` local environment like so:

```
pyenv virtualenv 3.12 swccdc-ephemeralizer
```

The `.python-version` file in the repository should be automatically picked up by pyenv.

Install dependencies by navigating to the root of the repository, and:

```
pip install .
```

## Installing

Use `pipx` to install this:

```
pipx install git+ssh://git@github.com/SouthwestCCDC/ephemeralizer
```
