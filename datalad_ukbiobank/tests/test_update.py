import sys
import os
from mock import patch

from datalad.api import (
    create,
)
from datalad.tests.utils import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_status,
    with_tempfile,
)
from datalad_ukbiobank.tests import (
    make_datarecord_zips,
)


# code of a fake ukbfetch drop-in
ukbfetch_code = """\
#!{pythonexec}

import shutil
from pathlib import Path

for line in open('.ukbbatch'):
    rec = '_'.join(line.split())
    for ext in ('zip', 'adv', 'txt'):
        testpath = Path('{basepath}', '%s.%s' % (rec, ext))
        if testpath.exists():
            shutil.copyfile(str(testpath), testpath.name)
"""


def make_ukbfetch(ds, records):
    # fake ukbfetch
    bin_dir = ds.pathobj / '.git' / 'tmp'
    bin_dir.mkdir()
    ukbfetch_file = bin_dir / 'ukbfetch'
    ukbfetch_file.write_text(
        ukbfetch_code.format(
            pythonexec=sys.executable,
            basepath=records,
        )
    )
    ukbfetch_file.chmod(0o744)
    return bin_dir


@with_tempfile
@with_tempfile(mkdir=True)
def test_base(dspath, records):
    # make fake UKB datarecord downloads
    make_datarecord_zips('12345', records)

    # init dataset
    ds = create(dspath)
    ds.ukb_init(
        '12345',
        ['20227_2_0', '25747_2_0', '25748_2_0', '25748_3_0'])
    # dummy key file, no needed to bypass tests
    ds.config.add('datalad.ukbiobank.keyfile', 'dummy', where='local')

    # fake ukbfetch
    bin_dir = make_ukbfetch(ds, records)

    # refuse to operate on dirty datasets
    (ds.pathobj / 'dirt').write_text('dust')
    assert_status('error', ds.ukb_update(on_failure='ignore'))
    (ds.pathobj / 'dirt').unlink()

    # meaningful crash with no ukbfetch
    assert_raises(RuntimeError, ds.ukb_update)

    # put fake ukbfetch in the path and run
    with patch.dict('os.environ', {'PATH': '{}:{}'.format(
            str(bin_dir),
            os.environ['PATH'])}):
        ds.ukb_update(merge=True)

    # get expected file layout
    incoming = ds.repo.get_files('incoming')
    incoming_p = ds.repo.get_files('incoming-native')
    for i in ['12345_25748_2_0.txt', '12345_25748_3_0.txt', '12345_20227_2_0.zip']:
        assert_in(i, incoming)
    for i in ['25748_2_0.txt', '25748_3_0.txt', '20227_2_0/fMRI/rfMRI.nii.gz']:
        assert_in(i, incoming_p)
    # not ZIPs after processing
    assert_not_in('12345_20227_2_0.zip', incoming_p)
    assert_not_in('20227_2_0.zip', incoming_p)

    # rerun works
    with patch.dict('os.environ', {'PATH': '{}:{}'.format(
            str(bin_dir),
            os.environ['PATH'])}):
        ds.ukb_update(merge=True)

    # rightfully refuse to merge when active branch is an incoming* one
    ds.repo.checkout('incoming')
    with patch.dict('os.environ', {'PATH': '{}:{}'.format(
            str(bin_dir),
            os.environ['PATH'])}):
        assert_in_results(
            ds.ukb_update(merge=True, force=True, on_failure='ignore'),
            status='impossible',
            message='Refuse to merge into incoming* branch',)


@with_tempfile
@with_tempfile(mkdir=True)
def test_bids(dspath, records):
    # make fake UKB datarecord downloads
    make_datarecord_zips('12345', records)

    # init dataset
    ds = create(dspath)
    ds.ukb_init(
        '12345',
        ['20227_2_0', '25747_2_0', '25748_2_0', '25748_3_0'],
        bids=True)
    # dummy key file, no needed to bypass tests
    ds.config.add('datalad.ukbiobank.keyfile', 'dummy', where='local')
    bin_dir = make_ukbfetch(ds, records)

    # put fake ukbfetch in the path and run
    with patch.dict('os.environ', {'PATH': '{}:{}'.format(
            str(bin_dir),
            os.environ['PATH'])}):
        ds.ukb_update(merge=True)

    bids_files = ds.repo.get_files('incoming-bids')
    master_files = ds.repo.get_files()
    for i in [
            'ses-2/func/sub-12345_ses-2_task-rest_bold.nii.gz',
            'ses-2/non-bids/fMRI/sub-12345_ses-2_task-hariri_eprime.txt',
            'ses-3/non-bids/fMRI/sub-12345_ses-3_task-hariri_eprime.txt']:
        assert_in(i, bids_files)
        assert_in(i, master_files)

    # run again, nothing bad happens
    with patch.dict('os.environ', {'PATH': '{}:{}'.format(
            str(bin_dir),
            os.environ['PATH'])}):
        ds.ukb_update(merge=True, force=True)

    bids_files = ds.repo.get_files('incoming-bids')
    master_files = ds.repo.get_files()
    for i in [
            'ses-2/func/sub-12345_ses-2_task-rest_bold.nii.gz',
            'ses-2/non-bids/fMRI/sub-12345_ses-2_task-hariri_eprime.txt',
            'ses-3/non-bids/fMRI/sub-12345_ses-3_task-hariri_eprime.txt']:
        assert_in(i, bids_files)
        assert_in(i, master_files)

    # now re-init with a different record subset and rerun
    ds.ukb_init('12345', ['25747_2_0.adv', '25748_2_0', '25748_3_0'],
                bids=True, force=True)
    with patch.dict('os.environ', {'PATH': '{}:{}'.format(
            str(bin_dir),
            os.environ['PATH'])}):
        ds.ukb_update(merge=True, force=True)
