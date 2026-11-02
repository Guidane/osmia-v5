"""How Osmia's tests run (settings.TEST_RUNNER).

- Spread over every processor, unless told otherwise (manage.py test --parallel 1: one at a time).
- On Windows the processes are started anew ("spawn"), and Django's spawn set-up expects an in-memory test database;
  Osmia's is a file (see settings.DATABASES), so each process opens its own copy of it, as Django does with "fork".
- manage.py test --slowest 20: the 20 slowest tests and class set-ups (installing templates, ...), one at a time.
"""
import time
import unittest

from django.db.backends.sqlite3.creation import DatabaseCreation
from django.test.runner import DiscoverRunner, ParallelTestSuite, _init_worker, get_max_test_processes

_django_setup_worker = DatabaseCreation.setup_worker_connection


def _setup_worker_connection(self, _worker_id):
    if self.is_in_memory_db(self.connection.settings_dict['NAME']):
        return _django_setup_worker(self, _worker_id)
    self.connection.settings_dict.update(self.get_test_db_clone_settings(_worker_id))   # this process's copy
    self.connection.close()


def init_worker(*args, **kwargs):
    """Each test process: its own copy of the file test database, then Django's set-up."""
    DatabaseCreation.setup_worker_connection = _setup_worker_connection
    return _init_worker(*args, **kwargs)


class Suite(ParallelTestSuite):
    init_worker = init_worker


class TimedResult(unittest.TextTestResult):
    """Notes how long each test takes, and the time before a class's first test (its set-up) for the class."""
    times, setups = {}, {}

    def startTest(self, test):
        now = time.perf_counter()
        if test.__class__ is not getattr(self, '_last_class', None):
            name = f'{test.__class__.__module__}.{test.__class__.__name__}'
            self.setups[name] = now - getattr(self, '_last_stop', now)
            self._last_class = test.__class__
        self._started = now
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        self._last_stop = time.perf_counter()
        self.times[test.id()] = self._last_stop - self._started


class Runner(DiscoverRunner):
    parallel_test_suite = Suite

    def __init__(self, parallel=0, slowest=0, **kwargs):
        self.slowest = slowest
        super().__init__(parallel=1 if slowest else (parallel or get_max_test_processes()), **kwargs)

    @classmethod
    def add_arguments(cls, parser):
        super().add_arguments(parser)
        parser.add_argument('--slowest', type=int, default=0, metavar='N',
                            help='Show the N slowest tests and class set-ups (runs the tests one at a time).')

    def get_resultclass(self):
        return TimedResult if self.slowest else super().get_resultclass()

    def suite_result(self, suite, result, **kwargs):
        if self.slowest:
            for title, times in (('tests', TimedResult.times), ('class set-ups', TimedResult.setups)):
                print(f'\nSlowest {title}:')
                for name, seconds in sorted(times.items(), key=lambda kv: -kv[1])[:self.slowest]:
                    print(f'  {seconds:7.2f}s  {name}')
        return super().suite_result(suite, result, **kwargs)
