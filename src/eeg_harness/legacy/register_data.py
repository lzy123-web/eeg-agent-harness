"""Legacy process-global EEG store migrated from EEGAgent.

This exists only to reproduce the audited baseline. It must be replaced before
concurrent or multi-record execution is introduced.
"""

_register_data = None


def registerData(data):
    global _register_data
    _register_data = data


def clearRegisteredData():
    global _register_data
    _register_data = None


def getRegisteredData(s=None, e=None, config=None):
    if _register_data is None:
        raise RuntimeError("EEG data is not registered; call registerData first")
    if s is not None and e is not None and config is not None:
        fs = config["fs"]
        return _register_data[:, s * fs:e * fs]
    return _register_data
