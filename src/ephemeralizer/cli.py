import click
import minio
import logging
import re
import os.path

import truststore
truststore.inject_into_ssl()

eph_log = logging.getLogger(__name__)

def get_minio_connection(remote_url, remote_access_key, remote_secret_key):
    eph_log.info(f'Connecting to remote minio endpoint at {remote_url}')
    # TODO: Trust our key, use truststore
    return minio.Minio(remote_url, access_key=remote_access_key, secret_key=remote_secret_key)

def load_defaults_from_config(config_path):
    # If the config file is not readable or doesn't exist, return an empty dictionary.
    if not os.path.exists(config_path) or not os.access(config_path, os.R_OK):
        eph_log.warning(f'Config file {config_path} is not readable or does not exist')
        return dict()

    config_schema = {
        'remote_url': 'EPH_URL',
        'remote_bucket': 'EPH_BUCKET',
        'remote_access_key': 'EPH_ACCESS_KEY',
        'remote_secret_key': 'EPH_SECRET_KEY'
    }
    default_arguments = dict()

    with open(config_path, 'r') as config_file:
        config = config_file.read()
        for arg, env_var in config_schema.items():
            match = re.search(f'{env_var}="(.+)"', config)
            if match:
                eph_log.debug(f'Found {arg} in config file')
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
@click.option('--remote-access-key', required=True, help='Access key for the remote minio endpoint')
@click.option('--remote-secret-key', required=True, help='Secret key for the remote minio endpoint')
def test(remote_url, remote_bucket, remote_access_key, remote_secret_key):
    try:
        client = get_minio_connection(remote_url, remote_access_key, remote_secret_key)
        found = client.bucket_exists(remote_bucket)
        eph_log.info(f'Connection to endpoint {remote_url} successful')
        if not found:
            eph_log.error(f'Bucket {remote_bucket} does not exist')
            return
    except ValueError as e:
        # "Path in endpoint is not allowed"
        eph_log.error(f'Error connecting to remote minio endpoint: {e}')
        return
    except minio.error.InvalidResponseError as e:
        eph_log.error(f"Got an invalid response from the remote endpoint: is it correct and running minio?")
        return
    except Exception as e:
        eph_log.error(f'Error connecting to remote minio endpoint: {e}')
        return
    


@ephemeralizer.command('save')
@click.pass_context
@click.option('--remote-url', required=True, help='URL of the remote minio endpoint')
@click.option('--remote-bucket', required=True, help='Name of the remote bucket')
@click.option('--remote-access-key', required=True, help='Access key for the remote minio endpoint')
@click.option('--remote-secret-key', required=True, help='Secret key for the remote minio endpoint')
@click.option('--local-path', required=True, type=click.Path(exists=True, file_okay=False, readable=True, dir_okay=True), help='Path to the local directory to be uploaded')
def save(ctx, remote_url, remote_bucket, remote_access_key, remote_secret_key, local_path):
    try:
        client = get_minio_connection(remote_url, remote_access_key, remote_secret_key)
    except ValueError as e:
        # "Path in endpoint is not allowed"
        eph_log.error(f'Error connecting to remote minio endpoint: {e}')
        return
    except Exception as e:
        eph_log.error(f'Error connecting to remote minio endpoint: {e}')
        return

def ephemeralize_app():
    ephemeralizer()
