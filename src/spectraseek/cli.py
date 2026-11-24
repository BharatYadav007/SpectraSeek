"""CLI for reproducible experiments and operator-controlled authorized surveys."""

import argparse
import json
from pathlib import Path
import sys

from .dataset import load_csv
from .experiment import RECOMMENDATION_STRATEGIES, evaluate, recommend


def _output_path(output: str) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='spectraseek')
    sub = parser.add_subparsers(dest='command', required=True)

    demo = sub.add_parser('demo')
    demo.add_argument('--output', default='data/synthetic.csv')
    demo.add_argument('--seed', type=int, default=42)
    demo.add_argument('--sessions', type=int, default=40)
    demo.add_argument('--scenario', choices=['stationary', 'interference', 'drift'], default='stationary')

    evaluation = sub.add_parser('evaluate')
    evaluation.add_argument('dataset')
    evaluation.add_argument('--budget', type=int, default=3)
    evaluation.add_argument('--windows', type=int, default=1, help='Number of chronological evaluation windows')
    evaluation.add_argument('--seed', type=int, default=42, help='Seed for random plans and bootstrap intervals')
    evaluation.add_argument('--output', default='results/evaluation.json')

    sensitivity = sub.add_parser('study', help='Offline adaptive and fixed budget comparison')
    sensitivity.add_argument('dataset')
    sensitivity.add_argument('--budgets', type=int, nargs='+', required=True)
    sensitivity.add_argument('--windows', type=int, default=1)
    sensitivity.add_argument('--temporal', action='store_true', help='Include lagged-history experimental predictors')
    sensitivity.add_argument('--output', default='results/study.json')

    recommendation = sub.add_parser('recommend')
    recommendation.add_argument('dataset')
    recommendation.add_argument('--visited', nargs='*', default=[])
    recommendation.add_argument('--found', nargs='*', default=[])
    recommendation.add_argument('--strategy', choices=RECOMMENDATION_STRATEGIES, default='random_forest')

    sub.add_parser('interfaces')
    sub.add_parser('init-db')
    export = sub.add_parser('export')
    export.add_argument('--output', default='data/measured.csv')
    scan = sub.add_parser('scan')
    scan.add_argument('--session', required=True)
    scan.add_argument('--site', required=True)
    scan.add_argument('--config', required=True)
    scan.add_argument('--interface')
    scan.add_argument('--authorized', action='store_true', required=True)

    pilot = sub.add_parser('pilot-collect', help='Collect authorized scans on a shared UTC schedule')
    pilot.add_argument('--config', required=True)
    pilot.add_argument('--site', required=True)
    pilot.add_argument('--start', required=True, help='Common future ISO-8601 timestamp with UTC offset')
    pilot.add_argument('--rounds', type=int, default=24)
    pilot.add_argument('--interval', type=int, default=60, help='Seconds between scheduled starts')
    pilot.add_argument('--interface')
    pilot.add_argument('--output', required=True)
    pilot.add_argument('--authorized', action='store_true', required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            from .scenarios import simulate_scenario

            data = simulate_scenario(args.seed, args.sessions, scenario=args.scenario)
            path = _output_path(args.output)
            data.to_csv(path, index=False)
            print(f'Wrote {len(data)} SYNTHETIC records to {path}')
        elif args.command == 'evaluate':
            result = evaluate(load_csv(args.dataset), args.budget, args.seed, windows=args.windows)
            path = _output_path(args.output)
            path.write_text(
                json.dumps(result, indent=2, allow_nan=False) + '\n',
                encoding='utf-8', newline='\n',
            )
            summary_fields = ('source', 'models', 'classification_baseline', 'strategies', 'coverage_vs_empirical')
            summary = {key: result[key] for key in summary_fields}
            print(json.dumps(summary, indent=2))
            print(f'Saved {path}')
        elif args.command == 'study':
            from .adaptive import study

            result = study(load_csv(args.dataset), args.budgets, windows=args.windows, include_temporal=args.temporal)
            path = _output_path(args.output)
            path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n',
                            encoding='utf-8', newline='\n')
            print(f'Saved {path}')
        elif args.command == 'recommend':
            result = recommend(load_csv(args.dataset), args.visited, args.found, args.strategy)
            print(json.dumps(result, indent=2))
        elif args.command == 'pilot-collect':
            from .pilot_collection import run

            return run(args)
        elif args.command == 'interfaces':
            from .collector import interfaces

            print('\n'.join(interfaces()))
        else:
            from .storage import SurveyRepository

            if args.command == 'scan':
                from .collector import scan as collect
                from .survey import SurveyConfig, survey_id

                config = SurveyConfig.load(args.config)
                site = survey_id(args.site)
                session = survey_id(args.session)
                if site not in config.sites:
                    raise ValueError(f'Unknown survey site: {site}')
                repository = SurveyRepository()
                repository.record(session, site, config, collect(args.interface))
                print('Recorded authorized target outcomes')
            elif args.command == 'init-db':
                SurveyRepository().initialize()
                print('Database schema ready')
            elif args.command == 'export':
                data = SurveyRepository().export()
                data.to_csv(_output_path(args.output), index=False)
                print(f'Exported {len(data)} measured rows')
        return 0
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
