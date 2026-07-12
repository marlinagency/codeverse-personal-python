from codeverse_core.theme_mapping.quality import assess_dictionary_quality


def test_quality_report_detects_long_repetitive_legacy_dictionary():
    report = assess_dictionary_quality(
        {
            "py_fn_bytes": "patrol_route_byte",
            "py_fn_callable": "patrol_route_can",
            "py_fn_compile": "patrol_route_build",
        },
        {
            "py_fn_bytes": "generic explanation",
            "py_fn_callable": "generic explanation",
            "py_fn_compile": "generic explanation",
        },
    )

    assert report.brevity_score == 0
    assert report.diversity_score == 0
    assert report.upgrade_recommended is True
    assert report.issues


def test_quality_report_rewards_short_distinct_behavior_mappings():
    report = assess_dictionary_quality(
        {
            "py_fn_bytes": "entry_packet",
            "py_fn_callable": "radio_ready",
            "py_fn_compile": "team_build",
        },
        {
            "py_fn_bytes": "entry cues an immutable packet of bytes.",
            "py_fn_callable": "radio cues checking whether a value can be called.",
            "py_fn_compile": "team cues turning source into executable code.",
        },
    )

    assert report.brevity_score == 100
    assert report.uniqueness_score == 100
    assert report.diversity_score == 100
    assert report.semantic_score == 100
    assert report.overall_score == 100
    assert report.upgrade_recommended is False
