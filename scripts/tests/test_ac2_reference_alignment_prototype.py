from scripts.ac2_reference_alignment_prototype_20261030 import warning


def test_device_does_not_establish_operating_system():
    assert warning('What is the operating system?', ['I watch films on a laptop.'])


def test_explicit_operating_system_not_flagged_by_this_rule():
    assert warning('What is the operating system?', ['My laptop runs Ubuntu.']) is None


def test_location_or_equipment_does_not_establish_work_arrangement():
    assert warning('What is the working arrangement?', ['The library is near my office.'])
    assert warning('What is the working arrangement?', ['My office printer is black and white.'])


def test_explicit_work_arrangement_and_other_question():
    assert warning('What is the working arrangement?', ['I work remotely.']) is None
    assert warning('What is the dietary preference?', ['I prefer vegetarian meals.']) is None
