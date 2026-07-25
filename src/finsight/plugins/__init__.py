"""Built-in FinSight plugins (drop-in sidebar extensions).

Any ``*.py`` file in this package — or in the user folder
``%LOCALAPPDATA%/FinSight/plugins/`` — that defines a
:class:`finsight.core.plugins.FinSightPlugin` subclass is discovered at
startup and mounted in the sidebar. Files starting with ``_`` are
ignored. See :mod:`finsight.core.plugins` for the contract.
"""
