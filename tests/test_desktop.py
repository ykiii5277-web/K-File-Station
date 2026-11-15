def test_native_widget_acceptance(tmp_path):
    from widget_check import run_checks
    from PIL import Image
    checks = run_checks(tmp_path / 'native-check')
    assert len(checks) == 40
    with Image.open(tmp_path / 'native-check/K挂件-紧凑圆盘弧形提示.png') as image:
        assert image.convert('RGBA').getpixel((0,0))[3] == 0
