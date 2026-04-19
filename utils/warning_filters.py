import warnings


def suppress_fuzzywuzzy_sequence_matcher_warning():
    warnings.filterwarnings(
        "ignore",
        message=r"Using slow pure-python SequenceMatcher.*",
        category=UserWarning,
        module=r"fuzzywuzzy\.fuzz",
    )
