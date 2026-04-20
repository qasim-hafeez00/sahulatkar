"""BUG-04 Regression Tests — Worker Entry Points.

Verifies that both scraping_worker.py and event_listener.py expose a
callable ``main()`` function so pyproject.toml entry-points work:

    scraping-worker = "src.workers.scraping_worker:main"
    event-listener  = "src.workers.event_listener:main"
"""
import importlib


def test_scraping_worker_has_callable_main():
    """scraping_worker.main() must exist and be callable by pyproject.toml."""
    module = importlib.import_module("src.workers.scraping_worker")
    fn = getattr(module, "main", None)
    assert callable(fn), (
        "scraping_worker.py must define a callable main() function for the "
        "pyproject.toml 'scraping-worker' entry point.  Without it, starting "
        "the worker via 'scraping-worker' CLI fails with ImportError."
    )


def test_event_listener_has_callable_main():
    """event_listener.main() must exist and be callable by pyproject.toml."""
    module = importlib.import_module("src.workers.event_listener")
    fn = getattr(module, "main", None)
    assert callable(fn), (
        "event_listener.py must define a callable main() function for the "
        "pyproject.toml 'event-listener' entry point.  Without it, starting "
        "the listener via 'event-listener' CLI fails with ImportError."
    )


def test_checkout_consumer_has_callable_main():
    """checkout_consumer.main() must remain callable (pre-existing, guard regression)."""
    module = importlib.import_module("src.workers.checkout_consumer")
    fn = getattr(module, "main", None)
    assert callable(fn), (
        "checkout_consumer.py must define a callable main() function."
    )
