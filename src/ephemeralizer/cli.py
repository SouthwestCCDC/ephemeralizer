import click
import minio
import logging
import re
import os.path
from io import BytesIO
from pathlib import Path

# TODO: Add quiesce and unquiesce commands

import truststore
truststore.inject_into_ssl()

TEST_FILE = '.ephemeralizer-test'

eph_log = logging.getLogger(__name__)

def composed_decorators(*decs):
    def deco(f):
        for dec in reversed(decs):
            f = dec(f)
        return f
    return deco

shared_command_options = composed_decorators(
    click.option('--remote-url', required=True, help='URL of the remote minio endpoint'),
    click.option('--remote-bucket', required=True, help='Name of the remote bucket'),
    click.option('--remote-prefix', required=True, help='Name of the prefix (directory) inside the bucket to use for this service'),
    click.option('--remote-access-key', required=True, help='Access key for the remote minio endpoint'),
    click.option('--remote-secret-key', required=True, help='Secret key for the remote minio endpoint'),
)

def get_minio_connection(remote_url, remote_access_key, remote_secret_key):
    eph_log.info(f'Connecting to remote minio endpoint at {remote_url}')
    # TODO: Trust our key, use truststore
    try:
        return minio.Minio(remote_url, access_key=remote_access_key, secret_key=remote_secret_key)
    except ValueError as e:
        # "Path in endpoint is not allowed"
        eph_log.error(f'Error setting minio endpoint: {e}')
        exit(1)
    except Exception as e:
        eph_log.error(f'Error connecting to minio endpoint: {e}')
        exit(1)

def load_defaults_from_config(config_path):
    # If the config file is not readable or doesn't exist, return an empty dictionary.
    if not os.path.exists(config_path) or not os.access(config_path, os.R_OK):
        eph_log.warning(f'Config file `{config_path}` is not readable or does not exist')
        return dict()

    eph_log.debug(f'Reading default arguments from config file `{config_path}`')

    config_schema = {
        'remote_url': 'EPH_URL',
        'remote_bucket': 'EPH_BUCKET',
        'remote_prefix': 'EPH_PREFIX',
        'remote_access_key': 'EPH_ACCESS_KEY',
        'remote_secret_key': 'EPH_SECRET_KEY'
    }
    default_arguments = dict()

    with open(config_path, 'r') as config_file:
        config = config_file.read()
        for arg, env_var in config_schema.items():
            match = re.search(f'{env_var}="(.+)"', config)
            if match:
                eph_log.debug(f'Read default `{arg}` from config file')
                default_arguments[arg] = match.group(1)

    return default_arguments

@click.group()
@click.pass_context
@click.option('--context-path', type=click.Path(file_okay=True, dir_okay=False, readable=True), 
              default="/var/run/one-context/one_env", 
              help='Path to the OpenNebula context file to read')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), default='INFO', help='Set the log level')
def ephemeralizer(ctx, context_path, log_level):
    ctx.ensure_object(dict)
    
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    eph_log.addHandler(handler)
    eph_log.setLevel(log_level)

    # The order of precedence for defaults is:
    #  1. Command line arguments overrule everything
    #  2. Environment variables overrule config file
    #  3. Anything from the config file overrules built-in defaults
    #  4. Built-in defaults (if any)

    default_args = load_defaults_from_config(context_path)

    if not ctx.default_map:
        ctx.default_map = dict()
    if ctx.invoked_subcommand not in ctx.default_map:
        ctx.default_map[ctx.invoked_subcommand] = dict()
    ctx.default_map[ctx.invoked_subcommand].update(default_args)

    # Next, ctx.invoked_subcommand will be called.

@ephemeralizer.command('test')
@shared_command_options
def test(remote_url, remote_bucket, remote_prefix, remote_access_key, remote_secret_key):
    try:
        # Connect, although lazily so this tells us nothing.
        client = get_minio_connection(remote_url, remote_access_key, remote_secret_key)
        # Try to find our bucket - actually exercise the connection.
        eph_log.debug(f'Attempting to find bucket {remote_bucket}')
        found = client.bucket_exists(remote_bucket)
        eph_log.info(f'Connection to endpoint {remote_url} successful')
        if not found:
            eph_log.error(f'Bucket {remote_bucket} does not exist')
            exit(1)
        test_file_path = f"{remote_prefix}/{TEST_FILE}"
        # Try to write a blank file to the bucket.
        eph_log.debug(f'Writing a blank file to {remote_bucket}/{test_file_path}')
        res = client.put_object(remote_bucket, test_file_path, BytesIO(b''), 0)
        eph_log.info(f'Successfully wrote {remote_bucket}/{test_file_path}')

        # TODO:
        # Technically, our permissions model says we shouldn't be able to read the
        #  file back. Try anyway, and WARN if we can read it.

        # We don't strictly need to be able to delete this file, but try anyway.
        eph_log.debug(f'Deleting {remote_bucket}/{test_file_path}')
        # TODO: Test this without permissions to delete
        res = client.remove_object(remote_bucket, test_file_path)
        eph_log.info(f'Successfully deleted {remote_bucket}/{test_file_path}')
    except minio.error.InvalidResponseError as e:
        eph_log.error(f"Got an invalid response from the remote endpoint: is it correct and running minio?")
        exit(1)
    except Exception as e:
        eph_log.error(f'{type(e)} {e}')
        exit(1)

@ephemeralizer.command('load')
@shared_command_options
@click.option('--local-path', required=True, type=click.Path(exists=True, file_okay=False, readable=True, writable=True, dir_okay=True), help='Path to the local directory to be uploaded')
def load(remote_url, remote_bucket, remote_prefix, remote_access_key, remote_secret_key, local_path):
    # TODO: Should we check to see if the local directory is empty?
    # TODO: Should we just be using mcli instead of this?
    local_path = Path(local_path)

    try:
        client = get_minio_connection(remote_url, remote_access_key, remote_secret_key)
        eph_log.debug(f'Attempting to find bucket {remote_bucket}')
        found = client.bucket_exists(remote_bucket)
        if not found:
            eph_log.error(f'Bucket {remote_bucket} does not exist')
            exit(1)
        eph_log.info(f'Connection to endpoint {remote_url} successful')
        eph_log.debug(f'Walking bucket {remote_bucket}/{remote_prefix}/*')
        remote_objects = client.list_objects(remote_bucket, prefix=remote_prefix, recursive=True)
        eph_log.info(f'Fetched list of objects at {remote_bucket}/{remote_prefix}/*')
        for obj in remote_objects:
            eph_log.debug(f'Found remote object {obj.object_name}')
            obj_relpath_parts = Path(obj.object_name).parts[1:]
            save_path = local_path.joinpath(*obj_relpath_parts)
            eph_log.debug(f'Placing found object at {save_path}')
            save_path.parent.mkdir(parents=True, exist_ok=True)
            client.fget_object(remote_bucket, obj.object_name, str(save_path))
            eph_log.info(f'Successfully downloaded {obj.object_name} to {save_path}')
        eph_log.info(f'Finished downloading all objects from {remote_bucket}/{remote_prefix}')
    except minio.error.InvalidResponseError as e:
        eph_log.error(f"Got an invalid response from the remote endpoint: is it correct and running minio?")
        exit(1)
    except Exception as e:
        eph_log.error(f'{type(e)} {e}')
        exit(1)

# TODO: Handle deleting files from the remote bucket if they don't exist locally?
@ephemeralizer.command('save')
@shared_command_options
@click.option('--local-path', required=True, type=click.Path(exists=True, file_okay=False, readable=True, dir_okay=True), help='Path to the local directory to be uploaded')
def save(remote_url, remote_bucket, remote_prefix, remote_access_key, remote_secret_key, local_path):
    local_path = Path(local_path)

    try:
        client = get_minio_connection(remote_url, remote_access_key, remote_secret_key)
        eph_log.debug(f'Attempting to find bucket {remote_bucket}')
        found = client.bucket_exists(remote_bucket)
        if not found:
            eph_log.error(f'Bucket {remote_bucket} does not exist')
            exit(1)
        eph_log.info(f'Connection to endpoint {remote_url} successful')
        eph_log.debug(f'Walking local directory {local_path}/*')
        for root, dirs, files in os.walk(local_path):
            for file in files:
                local_file_path = Path(root).joinpath(file)
                remote_file_path = f"{remote_prefix}/{local_file_path.relative_to(local_path)}"
                eph_log.debug(f'Uploading {local_file_path} to {remote_bucket}/{remote_prefix}')
                client.fput_object(remote_bucket, remote_file_path, str(local_file_path))
                eph_log.info(f'Successfully uploaded {local_file_path} to {remote_bucket}/{remote_prefix}')
        eph_log.info(f'Finished uploading all objects from {local_path} to {remote_bucket}/{remote_prefix}')
    except minio.error.InvalidResponseError as e:
        eph_log.error(f"Got an invalid response from the remote endpoint: is it correct and running minio?")
        exit(1)
    except Exception as e:
        eph_log.error(f'{type(e)} {e}')
        exit(1)

def ephemeralize_app():
    ephemeralizer()
