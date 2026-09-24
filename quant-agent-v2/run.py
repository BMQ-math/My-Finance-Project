#!/usr/bin/env python3
"""Launcher for a single general-purpose Researcher–Critic pair."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.codex_session import SessionError
from src.coordinator import load_config
from src.research_pair import PairError, ResearchPair

ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='quant', description='Run one Researcher–Critic pair with Codex.')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.toml', help='Workflow TOML configuration')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='Start a new pair run for a supplied question')
    run.add_argument('question', type=Path, help='UTF-8 file containing your research question')
    run.add_argument('--input', type=Path, action='append', default=[], dest='inputs',
                     help='Explicitly authorized local input file; repeat for multiple files')
    run.add_argument('--run-dir', type=Path, required=True, help='New directory; existing runs are never overwritten')
    run.add_argument('--timeout', type=float, help='Per-turn timeout in seconds; overrides pair.timeout_seconds')
    run.add_argument('--max-reviews', type=int, help='Maximum Critic reviews, including the first')
    for name, help_text in (
        ('status', 'Read saved status without starting workers'),
        ('resume', 'Continue only a known safe saved checkpoint'),
        ('stop', 'Ask the owning coordinator to stop its current worker'),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument('run_dir', type=Path)
    commands.add_parser('runs', help='List run directories under configured artifacts.root')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {'status', 'resume', 'stop'}:
            pair = ResearchPair.load(args.run_dir)
            if args.command == 'stop':
                result = pair.request_stop()
            elif args.command == 'status':
                result = pair.state
            else:
                result = pair.execute(resume=True)
        else:
            config = load_config(args.config.expanduser().resolve())
            if args.command == 'runs':
                root = ROOT / config.get('artifacts', {}).get('root', '.quant/runs')
                if root.exists():
                    for path in sorted(root.iterdir()):
                        if path.is_dir():
                            print(path)
                return 0
            options = config.setdefault('pair', {})
            if args.timeout is not None:
                options['timeout_seconds'] = args.timeout
            if args.max_reviews is not None:
                options['max_reviews'] = args.max_reviews
            pair = ResearchPair.create(project_root=ROOT, config=config, question_file=args.question,
                                       inputs=args.inputs, run_dir=args.run_dir)
            print(f'Run record: {pair.root}', flush=True)
            result = pair.execute()
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command in {'status', 'stop'}:
            return 0
        return 0 if result.get('status') == 'passed' else 1
    except (OSError, ValueError, PairError, SessionError) as exc:
        print(f'quant: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
