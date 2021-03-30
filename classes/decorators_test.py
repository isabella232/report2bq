import logging
import unittest

from unittest import mock
from classes import decorators

EXCEPTION = Exception("I'm an exception!")


class MockValidator(object):

    def __init__(self, validator):
        # validator is a function that takes a single argument and returns a bool.
        self.validator = validator

    def __eq__(self, other):
        return bool(self.validator(other))


class RetryTest(unittest.TestCase):

  def dummy_function_for_mocking(self):
    return

  @mock.patch.object(logging, 'warning', autospec=True)
  def test_retry_and_fail(self, mock_logger):

    @decorators.retry((Exception,), backoff=2, delay=1)
    def _test_retry_and_fail(mock_function):
      # mock_function is set to raise an exception on each call, but each will
      # log the attempt, with the third and final exception being propagated.
      mock_function()

    mock_foo = mock.create_autospec(
        self.dummy_function_for_mocking, side_effect=EXCEPTION)
    with self.assertRaisesRegex(Exception, 'an exception!'):
      _test_retry_and_fail(mock_function=mock_foo)

    self.assertEqual(mock_logger.call_count, 3)

  @mock.patch.object(logging, 'warning', autospec=True)
  def test_retry_and_succeed(self, mock_logger):
    @decorators.retry((Exception,), backoff=2, delay=1)
    def _test_retry_and_succeed(mock_function):
      mock_function()

    mock_foo = mock.create_autospec(
        self.dummy_function_for_mocking, side_effect=[EXCEPTION, ''])
    _test_retry_and_succeed(mock_foo)
    self.assertEqual(mock_foo.call_count, 2)
    self.assertEqual(mock_logger.call_count, 1)
    mock_logger.assert_called_once_with(
      'Try %d: "%s" - retrying in %d seconds...',
      MockValidator(lambda x: isinstance(x, int)),
      MockValidator(lambda x: isinstance(x, Exception)),
      MockValidator(lambda x: isinstance(x, int)))


class TimeItTest(unittest.TestCase):

  @mock.patch.object(logging, 'info', autospec=True)
  def test_timer(self, mock_logger):
    def dummy_function_for_mocking():
      return

    @decorators.timeit
    def _test_timer():
      dummy_function_for_mocking()

    _test_timer()
    mock_logger.assert_called_once_with('%s %0.3fms', '_test_timer',
                                        MockValidator(lambda x: isinstance(x, float)))


class MeasureMemoryTest(unittest.TestCase):

  @mock.patch.object(logging, 'info', autospec=True)
  def test_measure_memory(self, mock_logger):
    def dummy_function_for_mocking():
      return

    @decorators.measure_memory
    def _test_measure_memory():
      dummy_function_for_mocking()

    _test_measure_memory()
    print(mock_logger.call_args_list)
    mock_logger.assert_any_call(
        'Function Name        : %s',
        MockValidator(lambda x: isinstance(x, str)))
    mock_logger.assert_any_call(
        'Execution time       : %0.3fms',
        MockValidator(lambda x: isinstance(x, float)))
    mock_logger.assert_any_call(
        'Current memory usage : %04.3fM',
        MockValidator(lambda x: isinstance(x, float)))
    mock_logger.assert_any_call(
        'Peak                 : %04.3fM',
        MockValidator(lambda x: isinstance(x, float)))


class LazyPropertyTest(unittest.TestCase):
  class Foo(object):
    @decorators.lazy_property
    def lazy_thing(self) -> str:
      return 'lazy'

  def test_lazy_thing(self):
    foo = LazyPropertyTest.Foo()
    self.assertFalse(hasattr(foo, '_lazy_lazy_thing'))
    self.assertEqual('lazy', foo.lazy_thing)
    self.assertTrue(hasattr(foo, '_lazy_lazy_thing'))


if __name__ == '__main__':
  unittest.main()