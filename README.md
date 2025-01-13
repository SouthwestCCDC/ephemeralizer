# Ephemeralizer

## Summary

This is a tool to create sparkling backups in the TALON Cyber League's private cloud.
The idea is to turn stateful instances into ephemeral instances you can set and forget,
then roll the instance at will. Hence, `ephemeralizer`.

It relies on a semi-persistent deployment of minio, which then itself syncs to AWS S3.

It bootstraps a single directory with content pulled from a service-specific location
in a minio S3 bucket, then regularly syncs the content of that directory back to the
bucket as it gets updates in the system.
