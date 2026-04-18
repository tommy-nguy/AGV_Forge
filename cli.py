#!/usr/bin/env python3
"""AGV Forge CLI - Command line interface for the video automation pipeline."""

import click
from pathlib import Path
from forge_core.config import get_config
from forge_jobs.channel_manager import ChannelManager
from forge_jobs.job_manager import JobManager

@click.group()
def cli():
    """AGV Forge - Automated Video Factory"""
    pass

@cli.group()
def channel():
    """Manage channel profiles."""
    pass

@channel.command("create")
@click.option("--name", prompt=True)
@click.option("--language", prompt=True)
@click.option("--storage", prompt=True, help="Storage root path")
def channel_create(name, language, storage):
    """Create a new channel."""
    config = get_config()
    mgr = ChannelManager(config.database_path)
    channel = mgr.create_channel(
        channel_name=name,
        channel_language=language,
        storage_root=storage,
        log_root=str(Path(storage) / "logs"),
        default_background_sound_id="bg_default"
    )
    click.echo(f"Channel created: {channel.channel_id}")

@channel.command("list")
def channel_list():
    """List all channels."""
    config = get_config()
    mgr = ChannelManager(config.database_path)
    for ch in mgr.list_channels():
        status = "✅" if ch.is_active else "❌"
        click.echo(f"{status} {ch.channel_id} - {ch.channel_name} ({ch.channel_language})")

@cli.group()
def job():
    """Manage processing jobs."""
    pass

@job.command("create")
@click.option("--channel", required=True)
@click.argument("input_files", nargs=-1, required=True)
def job_create(channel, input_files):
    """Create a new job from input files."""
    config = get_config()
    channel_mgr = ChannelManager(config.database_path)
    job_mgr = JobManager(config.database_path, channel_mgr)
    record = job_mgr.create_job(channel, list(input_files))
    click.echo(f"Job created: {record.job_id}")

@job.command("list")
@click.option("--channel", default=None)
def job_list(channel):
    """List jobs."""
    config = get_config()
    channel_mgr = ChannelManager(config.database_path)
    job_mgr = JobManager(config.database_path, channel_mgr)
    for job in job_mgr.list_jobs(channel):
        click.echo(f"{job.job_id} - {job.current_state} ({job.progress_percent}%)")

if __name__ == "__main__":
    cli()