"""Release update integrity, local data preservation, and recovery."""
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from update_windows import apply_files, rollback, unpack, release_urls
import update_windows


def put(root, name, data):
    p=root/name; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(data)


def test_update_preserves_stores_local_sources_and_settings_and_can_roll_back(tmp_path):
    installed=tmp_path/'installed'; staged=tmp_path/'release'; backup=tmp_path/'backup'
    put(installed,'webui/app.py','old')
    put(staged,'webui/app.py','new')
    put(staged,'new-file.txt','added')
    put(installed,'consolidation-data/store','approved')
    put(staged,'consolidation-data/store','overwritten')
    put(installed,'update-settings.json','custom feed')
    put(staged,'update-settings.json','release feed')
    old={'schema_version':1,'sources':[{'path':'local.pdf','sha256':'local'}]}
    new={'schema_version':1,'sources':[{'path':'shipped.pdf','sha256':'shipped'}]}
    put(installed,'data/catalog.json',json.dumps(old))
    put(staged,'data/catalog.json',json.dumps(new))
    changes=apply_files(staged,installed,backup)
    assert (installed/'webui/app.py').read_text()=='new'
    assert (installed/'consolidation-data/store').read_text()=='approved'
    assert (installed/'update-settings.json').read_text()=='custom feed'
    assert len(json.loads((installed/'data/catalog.json').read_text())['sources'])==2
    rollback(installed,backup,changes)
    assert (installed/'webui/app.py').read_text()=='old'
    assert not (installed/'new-file.txt').exists()
    assert json.loads((installed/'data/catalog.json').read_text())==old


def test_conflicting_pdf_rolls_back_preceding_changes(tmp_path):
    installed=tmp_path/'installed'; staged=tmp_path/'release'
    put(installed,'a.txt','old');put(staged,'a.txt','new')
    put(installed,'data/local.pdf','original');put(staged,'data/local.pdf','different')
    with pytest.raises(ValueError,match='PDF differs'):
        apply_files(staged,installed,tmp_path/'backup')
    assert (installed/'a.txt').read_text()=='old'
    assert (installed/'data/local.pdf').read_text()=='original'


@pytest.mark.parametrize('name',['../escape','NyayaBandhu/../escape','NyayaBandhu/.venv/file','NyayaBandhu/C:/file',r'NyayaBandhu/..\escape'])
def test_unsafe_archives_rejected(tmp_path,name):
    archive=tmp_path/'release.zip'
    with ZipFile(archive,'w') as bundle:bundle.writestr(name,'bad')
    with pytest.raises(ValueError):unpack(archive,tmp_path/'out')


def test_release_requires_zip_and_checksum(monkeypatch):
    data={'assets':[{'name':'NyayaBandhu-Windows-v5.zip','browser_download_url':'https://example.test/app.zip'}]}
    monkeypatch.setattr(update_windows,'fetch',lambda url:json.dumps(data).encode())
    with pytest.raises(ValueError):release_urls('https://example.test/feed')
    data['assets'].append({'name':'NyayaBandhu-Windows-v5.zip.sha256','browser_download_url':'https://example.test/app.sha256'})
    assert release_urls('https://example.test/feed')==('https://example.test/app.zip','https://example.test/app.sha256')


def test_installer_package_requires_complete_layout(tmp_path):
    archive=tmp_path/'release.zip'
    with ZipFile(archive,'w') as bundle:
        bundle.writestr('NyayaBandhu/start.bat','start')
    with pytest.raises(ValueError,match='Incomplete release'):
        unpack(archive,tmp_path/'incomplete')
    with ZipFile(archive,'w') as bundle:
        for name in ('release.json','requirements.txt','pyproject.toml','start.bat','webui/app.py'):
            bundle.writestr('NyayaBandhu/'+name,'content')
    assert (unpack(archive,tmp_path/'complete')/'start.bat').read_text()=='content'
