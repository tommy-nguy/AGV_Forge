#!/usr/bin/env python3
"""
AGV Forge CLI - Command line interface for the video automation pipeline.
"""

import click
import json
from pathlib import Path
from typing import Optional

from forge_core.config import get_config, ForgeConfig
from forge_core.logging_config import configure_logging, get_logger
from forge_core.workspace import WorkspaceManager
from forge_jobs import ChannelManager, JobManager
from forge_ingest import MediaValidator, MediaNormalizer, TranscriptEngine
from forge_planner import GeminiPlanner, PlannerValidator, PlannerRepairLoop
from forge_image import GeminiImageProvider, AssetManager
from forge_render import TimelineResolver, MoviePyEngine, ThumbnailGenerator
from forge_review import ScriptReviewGate, FinalReviewGate
from forge_publish import PublishManager

logger = get_logger(__name__)


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def cli(debug: bool):
    """AGV Forge - Automated Video Factory"""
    log_level = "DEBUG" if debug else "INFO"
    configure_logging(log_level=log_level)
    get_config()


# ------------------- Channel Commands -------------------
@cli.group()
def channel():
    """Manage channel profiles."""
    pass


@channel.command("create")
@click.option("--name", prompt=True, help="Channel name.")
@click.option("--language", prompt=True, help="Language code (vi, en).")
@click.option("--storage", prompt=True, help="Storage root path.")
@click.option("--category", default="", help="Channel category.")
@click.option("--voice-mode", default="trained_brand_voice",
              help="Voice mode (trained_brand_voice, manual_audio_import, skip_voice).")
def channel_create(name: str, language: str, storage: str, category: str, voice_mode: str):
    """Create a new channel profile."""
    config = get_config()
    mgr = ChannelManager(config.database_path)
    storage_path = Path(storage).expanduser().resolve()
    log_root = storage_path / "logs"

    channel = mgr.create_channel(
        channel_name=name,
        channel_language=language,
        channel_category=category,
        storage_root=str(storage_path),
        log_root=str(log_root),
        default_background_sound_id="bg_default",
        default_publish_timezone="Asia/Ho_Chi_Minh",
        default_voice_mode=voice_mode,
    )
    click.echo(f"✅ Channel created: {channel.channel_id}")
    click.echo(f"   Name: {channel.channel_name}")
    click.echo(f"   Language: {channel.channel_language}")
    click.echo(f"   Storage: {channel.storage_root}")


@channel.command("list")
def channel_list():
    """List all channels."""
    config = get_config()
    mgr = ChannelManager(config.database_path)
    channels = mgr.list_channels(include_inactive=True)
    if not channels:
        click.echo("No channels found.")
        return
    for ch in channels:
        status = "🟢" if ch.is_active else "🔴"
        click.echo(f"{status} {ch.channel_id} | {ch.channel_name} ({ch.channel_language})")


# ------------------- Job Commands -------------------
@cli.group()
def job():
    """Manage processing jobs."""
    pass


@job.command("create")
@click.option("--channel", required=True, help="Channel ID.")
@click.option("--brief", default="", help="Brief description for planner.")
@click.argument("input_files", nargs=-1, required=True)
def job_create(channel: str, brief: str, input_files: tuple):
    """Create a new job from input files."""
    config = get_config()
    channel_mgr = ChannelManager(config.database_path)
    job_mgr = JobManager(config.database_path, channel_mgr)

    metadata = {"brief": brief} if brief else {}
    record = job_mgr.create_job(
        channel_id=channel,
        input_assets=list(input_files),
        metadata=metadata,
    )
    click.echo(f"✅ Job created: {record.job_id}")
    click.echo(f"   Channel: {record.channel_id}")
    click.echo(f"   Workspace: {record.workspace_root}")


@job.command("list")
@click.option("--channel", default=None, help="Filter by channel ID.")
def job_list(channel: Optional[str]):
    """List jobs."""
    config = get_config()
    channel_mgr = ChannelManager(config.database_path)
    job_mgr = JobManager(config.database_path, channel_mgr)
    jobs = job_mgr.list_jobs(channel)
    if not jobs:
        click.echo("No jobs found.")
        return
    for job in jobs:
        state_color = {
            "published": "🟢",
            "failed": "🔴",
            "archived": "⚫",
        }.get(job.current_state, "🟡")
        click.echo(f"{state_color} {job.job_id} | {job.current_state} ({job.progress_percent}%) | {job.channel_id}")


@job.command("run")
@click.argument("job_id")
@click.option("--skip-review", is_flag=True, help="Skip review gates (auto-approve).")
def job_run(job_id: str, skip_review: bool):
    """
    Run the full pipeline for a job.
    Steps: Ingest → Transcript → Planner → Voice (skip) → Image → Render → Review → Publish.
    """
    config = get_config()
    channel_mgr = ChannelManager(config.database_path)
    job_mgr = JobManager(config.database_path, channel_mgr)
    record = job_mgr.get_job(job_id)
    workspace_root = Path(record.workspace_root)
    wm = WorkspaceManager(config)

    click.echo(f"🚀 Running job {job_id}...")

    # --- Step 1: Ingest & Normalize ---
    click.echo("📁 Ingesting media...")
    job_mgr.update_job_state(job_id, "ingesting")
    validator = MediaValidator()
    normalizer = MediaNormalizer()

    input_assets = record.input_assets
    raw_video = Path(input_assets[0]["workspace_path"])
    norm_video = workspace_root / "working" / "normalized_video.mp4"
    ext_audio = workspace_root / "working" / "extracted_audio.wav"

    media_info = validator.validate(raw_video)
    normalizer.normalize_video(raw_video, norm_video)
    normalizer.extract_audio(raw_video, ext_audio)

    job_mgr.update_job_state(job_id, "transcribing")

    # --- Step 2: Transcript ---
    click.echo("🎤 Transcribing audio...")
    transcript_engine = TranscriptEngine(model_name="base")
    transcript = transcript_engine.transcribe(ext_audio, language="vi")
    transcript_engine.save_transcript_json(transcript, workspace_root / "working" / "transcript.json")
    job_mgr.update_job_state(job_id, "planning")

    # --- Step 3: Planner ---
    click.echo("🧠 Planning with Gemini...")
    channel = channel_mgr.get_channel(record.channel_id)
    planner = GeminiPlanner(config)
    validator_planner = PlannerValidator()
    repair = PlannerRepairLoop(planner, validator_planner)

    import json
    schema_json = json.dumps(validator_planner.schema, indent=2)
    brief = record.input_assets[0].get("metadata", {}).get("brief", "")
    
    prompt = f"""
You are an AI video editor. Generate a JSON object strictly conforming to the provided schema.
Do NOT include markdown code blocks, explanations, or any text outside the JSON.
Output ONLY the JSON object, starting with {{ and ending with }}.

Schema:
{schema_json}

Channel: {channel.channel_name}
Transcript: {transcript['full_text']}
Brief: {brief}

JSON Output:
"""
    planner_output = repair.run_with_repair(prompt)

    with open(workspace_root / "manifest" / "planner_output.json", "w") as f:
        json.dump(planner_output, f, indent=2)
    job_mgr.update_job_state(job_id, "awaiting_script_review")

    if not skip_review:
        click.echo("⏸️  Job paused for script review. Use 'job review' command.")
        return
    else:
        job_mgr.update_job_state(job_id, "voice_rendering")

    # --- Step 4: Voice (ÉP BUỘC SKIP) ---
    click.echo("🔊 Rendering voice...")
    from pydub import AudioSegment
    master_audio = workspace_root / "assets" / "audio" / "master_audio.wav"
    master_audio.parent.mkdir(parents=True, exist_ok=True)
    # Tạo audio im lặng 5 giây
    AudioSegment.silent(duration=5000).export(master_audio, format="wav")
    click.echo("⏭️  Voice skipped (forced) – audio trống được tạo")
    job_mgr.update_job_state(job_id, "image_generating")

    # --- Step 5: Images ---
    click.echo("🎨 Generating images...")
    image_provider = GeminiImageProvider({"api_key": config.gemini_api_key})
    asset_mgr = AssetManager(workspace_root)
    for img_prompt in planner_output["image_prompts"]:
        temp = workspace_root / "working" / f"{img_prompt['asset_id']}.png"
        image_provider.generate_image(
            prompt=img_prompt["prompt"],
            output_path=temp,
            aspect_ratio=img_prompt.get("aspect_ratio", "16:9"),
            negative_prompt=img_prompt.get("negative_prompt"),
        )
        asset_mgr.register_image(img_prompt["asset_id"], temp, img_prompt)
    job_mgr.update_job_state(job_id, "rendering")

    # --- Step 6: Render ---
    click.echo("🎬 Rendering video...")
    resolver = TimelineResolver(workspace_root, asset_mgr)
    resolved = resolver.resolve(planner_output, master_audio)
    render_engine = MoviePyEngine(workspace_root)
    final_video = render_engine.render(resolved)
    job_mgr.update_job_state(job_id, "awaiting_final_review")

    # --- Step 7: Thumbnail ---
    thumb_gen = ThumbnailGenerator(image_provider, asset_mgr)
    thumbnail = thumb_gen.generate(
        planner_output["thumbnail_prompt"],
        planner_output.get("thumbnail_text")
    )

    if not skip_review:
        click.echo(f"⏸️  Job {job_id} ready for final review. Video: {final_video}")
        return
    else:
        job_mgr.update_job_state(job_id, "publishing")

    # --- Step 8: Publish ---
    click.echo("📤 Skipping publish (disabled for test run)...")
    job_mgr.update_job_state(job_id, "published")
    click.echo(f"🎉 Job {job_id} completed!")
    return


@job.command("review")
@click.argument("job_id")
@click.option("--approve", is_flag=True, help="Approve current review step.")
@click.option("--reject", is_flag=True, help="Reject and route back.")
@click.option("--reason", default="", help="Reason for rejection.")
def job_review(job_id: str, approve: bool, reject: bool, reason: str):
    """Review a job at script or final stage."""
    config = get_config()
    channel_mgr = ChannelManager(config.database_path)
    job_mgr = JobManager(config.database_path, channel_mgr)
    record = job_mgr.get_job(job_id)
    workspace_root = Path(record.workspace_root)
    wm = WorkspaceManager(config)
    state = record.current_state

    if state == "awaiting_script_review":
        gate = ScriptReviewGate(job_mgr, workspace_root)
        if approve:
            gate.approve()
            click.echo("✅ Script approved. Moving to voice stage.")
        elif reject:
            gate.reject(reason)
            click.echo(f"❌ Script rejected: {reason}")
        else:
            script = gate.get_current_script()
            click.echo(json.dumps(script["content_script"], indent=2))
    elif state == "awaiting_final_review":
        gate = FinalReviewGate(job_mgr, workspace_root)
        if approve:
            gate.approve()
            click.echo("✅ Final video approved. Publishing...")
        elif reject:
            gate.reject(reason, edit_issue=True)
            click.echo(f"❌ Final video rejected: {reason}")
        else:
            video_path = gate.get_video_path()
            click.echo(f"Video ready at: {video_path}")
    else:
        click.echo(f"Job is not in a review state (current: {state})")


if __name__ == "__main__":
    cli()