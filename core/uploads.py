"""Bounded document structure checks. These are not an antivirus scanner."""
import io
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from django import forms

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_EXPANDED_SIZE = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx'}


def validate_word_container(data):
    if not data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')) or len(data) < 512:
        raise ValueError('Invalid Word container')
    if data[28:30] != b'\xfe\xff': raise ValueError('Invalid container byte order')
    shift=struct.unpack_from('<H',data,30)[0]
    if shift not in (9,12): raise ValueError('Invalid sector size')
    sector_size=1 << shift
    sector_count=len(data)//sector_size-1
    fat_count=struct.unpack_from('<I',data,44)[0]
    if not 0 < fat_count <= 109: raise ValueError('Unsupported FAT layout')
    def sector(index):
        if index >= sector_count: raise ValueError('Sector outside document')
        start=(index+1)*sector_size
        return data[start:start+sector_size]
    fat=[]
    for index in struct.unpack_from('<109I',data,76)[:fat_count]:
        block=sector(index); fat.extend(struct.unpack('<'+'I'*(sector_size//4),block))
    current=struct.unpack_from('<I',data,48)[0]
    seen=set(); directory=b''
    while current != 0xfffffffe:
        if current in seen or len(seen)>1000 or current>=len(fat): raise ValueError('Invalid directory chain')
        seen.add(current); directory+=sector(current); current=fat[current]
    names=[]
    for offset in range(0,len(directory),128):
        entry=directory[offset:offset+128]
        length=struct.unpack_from('<H',entry,64)[0]
        if entry[66] == 0: continue
        if length < 2 or length > 64 or length % 2: raise ValueError('Invalid directory name')
        names.append(entry[:length-2].decode('utf-16le').casefold())
    if 'worddocument' not in names or not {'0table','1table'} & set(names): raise ValueError('Not a Word document')
    if set(names) & {'vba','macros','_vba_project_cur','objectpool'}: raise ValueError('Macros or embedded objects are not accepted')


def validate_upload(upload):
    if not upload:
        return upload
    extension = Path(upload.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise forms.ValidationError('Only PDF, DOC and DOCX files are allowed.')
    if upload.size > MAX_FILE_SIZE:
        raise forms.ValidationError('File must not exceed 5 MB.')
    position = upload.tell()
    try:
        upload.seek(0)
        data = upload.read(MAX_FILE_SIZE + 1)
        if len(data) > MAX_FILE_SIZE:
            raise ValueError('Too large')
        if extension == '.pdf':
            if not re.match(rb'%PDF-[12]\.\d', data) or b'%%EOF' not in data[-2048:] or b'startxref' not in data[-2048:]:
                raise ValueError('Invalid PDF structure')
            cross_reference=re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$',data)
            if not cross_reference: raise ValueError('Invalid PDF cross-reference')
            offset=int(cross_reference[1])
            if offset >= len(data): raise ValueError('PDF offset outside document')
            section=data[offset:offset+1024]
            if not section.startswith(b'xref') and not (re.match(rb'\d+\s+\d+\s+obj',section) and b'/XRef' in section):
                raise ValueError('Invalid PDF cross-reference target')
            if not re.search(rb'/Root\s+\d+\s+\d+\s+R',data): raise ValueError('Missing PDF document root')
            # Decode escaped PDF name characters before checking active-content names.
            decoded = re.sub(rb'#([0-9A-Fa-f]{2})', lambda match: bytes([int(match[1], 16)]), data)
            if re.search(rb'/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|OpenAction|AA)\b', decoded):
                raise ValueError('Active PDF content')
        elif extension == '.doc':
            validate_word_container(data)
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(entry.file_size for entry in entries) > MAX_EXPANDED_SIZE:
                    raise ValueError('Archive too large')
                names = archive.namelist()
                if len(names) != len(set(names)) or not {'[Content_Types].xml', 'word/document.xml'} <= set(names):
                    raise ValueError('Invalid Word package')
                for entry in entries:
                    name = entry.filename.lower()
                    if entry.flag_bits & 1 or name.startswith(('/', '\\')) or '..' in name.replace('\\', '/').split('/'):
                        raise ValueError('Unsafe archive entry')
                    if any(part in name for part in ('vbaproject', 'word/embeddings/', 'word/activex/')):
                        raise ValueError('Active Office content')
                    if entry.file_size > max(entry.compress_size, 1) * 200:
                        raise ValueError('Unsafe compression ratio')
                    if name.endswith('.xml') or name.endswith('.rels'):
                        xml = archive.read(entry)
                        if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                            raise ValueError('Unsafe XML declaration')
                        root = ElementTree.fromstring(xml)
                        if name == '[content_types].xml' and any('macroenabled' in str(node.attrib).lower() for node in root.iter()):
                            raise ValueError('Macro content type')
                        if name == 'word/document.xml' and root.tag != '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document':
                            raise ValueError('Invalid Word document XML')
                        if name.endswith('.rels') and any(node.attrib.get('TargetMode') == 'External' and not node.attrib.get('Type', '').endswith('/hyperlink') for node in root.iter()):
                            raise ValueError('External document resource')
    except (ValueError, zipfile.BadZipFile, RuntimeError, ElementTree.ParseError, NotImplementedError, EOFError, struct.error) as exc:
        raise forms.ValidationError('Upload a valid document without scripts, macros or embedded active content.') from exc
    finally:
        upload.seek(position)
    return upload
