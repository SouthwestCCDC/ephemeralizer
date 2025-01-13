import click
import minio
import logging
import re
import os.path
from io import BytesIO

# TODO: Add quiesce and unquiesce commands

# TODO: set a path inside the bucket as well as the bucket name, since it seems like we're
#       moving to using a single bucket.

import truststore
truststore.inject_into_ssl()

TEST_FILE = '.ephemeralizer-test'

eph_log = logging.getLogger(__name__)

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
@click.option('--remote-url', required=True, help='URL of the remote minio endpoint')
@click.option('--remote-bucket', required=True, help='Name of the remote bucket')
@click.option('--remote-prefix', required=True, help='Name of the prefix (directory) inside the bucket to use for this service')
@click.option('--remote-access-key', required=True, help='Access key for the remote minio endpoint')
@click.option('--remote-secret-key', required=True, help='Secret key for the remote minio endpoint')
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
            return
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
        return
    
    except Exception as e:
        eph_log.error(f'{type(e)} {e}')
        print(dir(e))
        print(e.with_traceback())
        return

# @ephemeralizer.command('save')
# @click.pass_context
# @click.option('--remote-url', required=True, help='URL of the remote minio endpoint')
# @click.option('--remote-bucket', required=True, help='Name of the remote bucket')
# @click.option('--remote-access-key', required=True, help='Access key for the remote minio endpoint')
# @click.option('--remote-secret-key', required=True, help='Secret key for the remote minio endpoint')
# @click.option('--local-path', required=True, type=click.Path(exists=True, file_okay=False, readable=True, dir_okay=True), help='Path to the local directory to be uploaded')
# def save(ctx, remote_url, remote_bucket, remote_access_key, remote_secret_key, local_path):
#     try:
#         client = get_minio_connection(remote_url, remote_access_key, remote_secret_key)

def ephemeralize_app():
    ephemeralizer()
