#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build MangoJuice (C:\\Program Files\\MangoJuice), the MangoHud settings GUI, for OrbisDesk (PE64).

MangoJuice-Windows (dependencies.lock.json "mangojuice", GPL-3.0) is a Vala program on GTK4,
libadwaita-1 and libgee. docs/MANGOJUICE.md has the route and its limits. Run in WSL Ubuntu-22.04:
  python3 tools/build-mangojuice-hw.py --fetch    # pinned downloads into .deps/mangojuice, then build
  python3 tools/build-mangojuice-hw.py            # build from what is already fetched
  python3 tools/build-mangojuice-hw.py --lock     # re-resolve the pins (writes mangojuice.lock.json)
Inputs, all checked by SHA-256 against mangojuice.lock.json:
  - MSYS2 ucrt64 packages: libadwaita and libgee with their dependency closure (headers, import
    libraries, DLLs, data), and vala for its vapis (Ubuntu's valac 0.56.0 has a GTK 4.6 gtk4.vapi);
  - Ubuntu 22.04 .debs for the host tools: valac and its libraries, zstd (MSYS2 packages are
    .tar.zst) and rsvg-convert (the icon);
  - llvm-mingw (dependencies.lock.json "llvm-mingw"): MSYS2's DLLs use the UCRT, and the distro's
    MinGW gcc 10 links msvcrt.
The source copy is revised in build/mangojuice-hw/src, as the other -hw builders revise theirs.
Vala makes C, llvm-mingw compiles and links it twice, and the two links must be identical.
The program, the DLLs it imports from the MSYS2 tree, GTK's schemas and icons, the licences of
those packages and an .ico from MangoJuice's own SVG go to out/mangojuice-hw/MangoJuice. The
manifest lists each file and the Windows DLLs the program needs from Wine; build-wine-hardware.py
checks them. ORBISDESK_DEPS names another .deps (a worktree uses the main checkout's).
"""
import argparse,hashlib,io,json,os,pathlib,re,shutil,struct,subprocess,tarfile,urllib.request,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
DEPS_ROOT=pathlib.Path(os.environ.get('ORBISDESK_DEPS',ROOT/'.deps'))
LOCK=ROOT/'mangojuice.lock.json'
DEPS=DEPS_ROOT/'mangojuice'
SOURCE=DEPS_ROOT/'vk/mangojuice-win'
work=ROOT/'build/mangojuice-hw';out=ROOT/'out/mangojuice-hw'
MSYS2_REPO='https://repo.msys2.org/mingw/ucrt64/'
PREFIX='mingw-w64-ucrt-x86_64-'
ROOT_PACKAGES=(PREFIX+'libadwaita',PREFIX+'libgee')
BUILD_PACKAGES=(PREFIX+'vala',)  # its share/vala-0.56/vapi only; nothing of it ships
DEBS=('valac','valac-bin','libvala-0.56-0','libvalacodegen-0.56-0','zstd','librsvg2-bin')
# MSYS2's vulkan-1.dll is not shipped: system32's is OrbisDesk's Khronos loader (build-wine-hardware.py)
NOT_SHIPPED={'vulkan-1.dll'}
# not needed to build or run: documentation, translations of other packages, Python, Tcl/Tk
EXCLUDE=re.compile(r'^ucrt64/(share/(doc|man|gtk-doc|info|locale|iso-codes|devhelp)|lib/(python3|tcl|tk)|include/(python3|tcl|tk))')
SIZES=(16,32,48)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def run(command,**kw):
    result=subprocess.run(command,capture_output=True,text=True,**kw)
    if result.returncode:raise SystemExit(' '.join(map(str,command))[:400]+'\n'+result.stdout[-2000:]+result.stderr[-4000:])
    return result.stdout

def read_db(path,zstd):
    raw=subprocess.run([zstd,'-dc',str(path)],capture_output=True,check=True).stdout
    db={};provides={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        for member in t:
            if not member.name.endswith('/desc'):continue
            fields={}
            for block in t.extractfile(member).read().decode().strip().split('\n\n'):
                lines=block.split('\n');fields[lines[0].strip('%')]=lines[1:]
            db[fields['NAME'][0]]=fields
            for p in fields.get('PROVIDES',[]):provides[re.split('[<>=]',p)[0]]=fields['NAME'][0]
    return db,provides

def lock():
    """re-resolve: MSYS2's current database and Ubuntu's current .debs (needs zstd on PATH or fetched)"""
    DEPS.mkdir(parents=True,exist_ok=True)
    zstd=shutil.which('zstd') or str(work/'tools/usr/bin/zstd')
    database=DEPS/'ucrt64.db';urllib.request.urlretrieve(MSYS2_REPO+'ucrt64.db',database)
    db,provides=read_db(database,zstd)
    def name(dep):
        d=re.split('[<>=]',dep)[0];return d if d in db else provides.get(d)
    seen=[];stack=list(ROOT_PACKAGES)
    while stack:
        n=name(stack.pop())
        if n and n not in seen:seen.append(n);stack+=db[n].get('DEPENDS',[])
    packages={}
    for n in sorted(seen)+list(BUILD_PACKAGES):
        f=db[n];packages[n]={'version':f['VERSION'][0],'filename':f['FILENAME'][0],'sha256':f['SHA256SUM'][0],
                             'bytes':int(f['CSIZE'][0]),'role':'build' if n in BUILD_PACKAGES else 'runtime closure'}
    debs={};folder=DEPS/'debs';folder.mkdir(exist_ok=True)
    for package in DEBS:
        run(['apt-get','download',package],cwd=folder)
        found=sorted(folder.glob(package+'_*.deb'))[-1]
        debs[package]={'filename':found.name,'version':found.name.split('_')[1],'sha256':sha(found)}
    source=json.loads((ROOT/'dependencies.lock.json').read_text())['repositories']['mangojuice']
    data={'schema_version':1,'generator':'tools/build-mangojuice-hw.py --lock',
          'source':{'name':'mangojuice','url':source['url'],'commit':source['commit']},
          'msys2':{'repository':MSYS2_REPO,'database_sha256':sha(database),'roots':list(ROOT_PACKAGES),
                   'packages':packages},
          'ubuntu':{'distribution':'Ubuntu 22.04 (jammy)','debs':debs},
          'toolchain':{'llvm-mingw':'dependencies.lock.json archives llvm-mingw'}}
    LOCK.write_text(json.dumps(data,indent=1)+'\n')
    print(json.dumps({'packages':len(packages),'debs':len(debs)}))

def fetch(pins):
    (DEPS/'pkgs').mkdir(parents=True,exist_ok=True);(DEPS/'debs').mkdir(exist_ok=True)
    for name,p in pins['msys2']['packages'].items():
        target=DEPS/'pkgs'/p['filename']
        if not target.exists() or sha(target)!=p['sha256']:
            urllib.request.urlretrieve(pins['msys2']['repository']+p['filename'],target)
    for name,d in pins['ubuntu']['debs'].items():
        target=DEPS/'debs'/d['filename']
        if not target.exists() or sha(target)!=d['sha256']:run(['apt-get','download',name+'='+d['version']],cwd=DEPS/'debs')

def png_rgba(data):
    """the RGBA rows of an 8-bit, non-interlaced RGBA PNG (rsvg-convert's output)"""
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise SystemExit('not a PNG')
    at=8;idat=b''
    while at<len(data):
        length,kind=struct.unpack('>I4s',data[at:at+8]);body=data[at+8:at+8+length];at+=12+length
        if kind==b'IHDR':
            width,height,depth,colour,_,_,interlace=struct.unpack('>IIBBBBB',body)
            if (depth,colour,interlace)!=(8,6,0):raise SystemExit('unexpected PNG format')
        elif kind==b'IDAT':idat+=body
    raw=zlib.decompress(idat);stride=width*4;rows=[];previous=bytearray(stride);at=0
    for _ in range(height):
        kind=raw[at];line=bytearray(raw[at+1:at+1+stride]);at+=1+stride
        for i in range(stride):
            a=line[i-4] if i>=4 else 0;b=previous[i];c=previous[i-4] if i>=4 else 0
            if kind==1:line[i]=(line[i]+a)&255
            elif kind==2:line[i]=(line[i]+b)&255
            elif kind==3:line[i]=(line[i]+(a+b)//2)&255
            elif kind==4:
                p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c)
                line[i]=(line[i]+(a if pa<=pb and pa<=pc else b if pb<=pc else c))&255
        rows.append([tuple(line[x*4:x*4+4]) for x in range(width)]);previous=line
    return rows
def ico(images):
    """the .ico layout of tools/make-icons.py: one 32-bit BMP with an AND mask per size"""
    header=struct.pack('<HHH',0,1,len(images));entries=b'';data=b'';offset=6+16*len(images)
    for size,pixels in images:
        xor=b''.join(bytes((p[2],p[1],p[0],p[3])) for row in reversed(pixels) for p in row)
        mask_row=((size+31)//32)*4;mask=b''
        for row in reversed(pixels):
            line=bytearray(mask_row)
            for i,p in enumerate(row):
                if p[3]==0:line[i//8]|=0x80>>(i%8)
            mask+=bytes(line)
        bmp=struct.pack('<IiiHHIIiiII',40,size,size*2,1,32,0,len(xor)+len(mask),0,0,0,0)+xor+mask
        entries+=struct.pack('<BBBBHHII',size,size,0,0,1,32,len(bmp),offset);data+=bmp;offset+=len(bmp)
    return header+entries+data

def build(pins):
    # inputs
    for name,p in pins['msys2']['packages'].items():
        path=DEPS/'pkgs'/p['filename']
        if not path.exists() or sha(path)!=p['sha256']:raise SystemExit('missing or changed (run --fetch): '+str(path))
    for name,d in pins['ubuntu']['debs'].items():
        path=DEPS/'debs'/d['filename']
        if not path.exists() or sha(path)!=d['sha256']:raise SystemExit('missing or changed (run --fetch): '+str(path))
    commit=run(['git','-C',str(SOURCE),'rev-parse','HEAD']).strip()
    if commit!=pins['source']['commit']:raise SystemExit('MangoJuice source is not the pinned commit: '+commit)
    if run(['git','-C',str(SOURCE),'status','--porcelain']).strip():raise SystemExit('MangoJuice source has local changes')
    archive=json.loads((ROOT/'dependencies.lock.json').read_text())['archives']['llvm-mingw']
    tarball=DEPS_ROOT/pathlib.Path(archive['path']).relative_to('.deps')
    if not tarball.exists() and args.fetch:  # tools/vk-h0/fetch-llvm-mingw.sh fetches it too; a cached graphics block may not
        tarball.parent.mkdir(parents=True,exist_ok=True);urllib.request.urlretrieve(archive['url'],tarball)
    if not tarball.exists() or sha(tarball)!=archive['sha256']:raise SystemExit('llvm-mingw archive differs from its pin')
    llvm=DEPS/('llvm-mingw-'+archive['version'])
    if not (llvm/'.orbis-sha256').exists() or (llvm/'.orbis-sha256').read_text()!=archive['sha256']:
        if llvm.exists():shutil.rmtree(llvm)
        llvm.mkdir(parents=True);run(['tar','-xJf',str(tarball),'-C',str(llvm),'--strip-components=1'])
        (llvm/'.orbis-sha256').write_text(archive['sha256'])
    clang=llvm/'bin/x86_64-w64-mingw32-clang';objdump=llvm/'bin/llvm-objdump'
    if work.exists():shutil.rmtree(work)
    tools=work/'tools';sysroot=work/'sysroot';src=work/'src';tools.mkdir(parents=True)
    for d in pins['ubuntu']['debs'].values():run(['dpkg-deb','-x',str(DEPS/'debs'/d['filename']),str(tools)])
    zstd=str(tools/'usr/bin/zstd')
    env=dict(os.environ,LD_LIBRARY_PATH=str(tools/'usr/lib/x86_64-linux-gnu')+':'+str(tools/'usr/lib/x86_64-linux-gnu/vala-0.56'))
    # the MSYS2 tree, and which package each file came from (for the licences)
    owner={}
    for name,p in pins['msys2']['packages'].items():
        raw=subprocess.run([zstd,'-dc',str(DEPS/'pkgs'/p['filename'])],capture_output=True,check=True,env=env).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            for member in t:
                if member.name.startswith('.') or EXCLUDE.match(member.name):continue
                if member.issym() or member.islnk() or '..' in member.name.split('/'):continue
                if member.isfile():
                    target=sysroot/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(t.extractfile(member).read());owner[member.name.lower()]=name
    usr=sysroot/'ucrt64'
    # the source, revised for OrbisDesk
    shutil.copytree(SOURCE/'src',src);shutil.copytree(SOURCE/'data',work/'data')
    revisions=[]
    def revise(path,old,new,why):
        target=work/path;text=target.read_text()
        if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
        target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})
    revise('src/mangojuice.vala','''        var app = new MangoJuice();
        return app.run(args);''','''        // OrbisDesk: the title has no GL for GTK, and its Vulkan is the games' (docs/MANGOJUICE.md);
        // cairo draws the window in software. Set only when the user has not set them.
        Environment.set_variable("GSK_RENDERER", "cairo", false);
        Environment.set_variable("GDK_DISABLE", "gl,vulkan", false);
        var app = new MangoJuice();
        return app.run(args);''','GTK draws with cairo; no GL or Vulkan context for the settings window.')
    # run-0062: text drawn through Wine's DirectWrite (pango's win32 font map, cairo's dwrite font faces) lost strokes
    # and letters; pango's fontconfig map draws with MSYS2's FreeType from C:\windows\Fonts (etc/fonts below).
    # Popovers, tooltips and the CSD window are transparent around a shadow, which GTK gets from DWM's blur-behind;
    # Wine composites no alpha, so that margin was black (the window's until maximized, run-0064). Without a shadow
    # or rounded corners those surfaces are opaque. A decorated CSD window still keeps a margin as wide as GTK's
    # resize handles (run-0066, the CSS alone left it black), so windows are undecorated: libadwaita draws its own
    # header bar and window buttons inside the window.
    revise('src/mangojuice.vala','''        var app = new MangoJuice();
        return app.run(args);''','''        Environment.set_variable("PANGOCAIRO_BACKEND", "fontconfig", false);
        var app = new MangoJuice();
        app.startup.connect (() => {
            var css = new Gtk.CssProvider ();
            css.load_from_string ("window, window.csd, window.background, popover, popover > contents, popover > arrow, tooltip { box-shadow: none; border-radius: 0; } popover > contents { margin: 0; }");
            Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (), css, Gtk.STYLE_PROVIDER_PRIORITY_USER);
        });
        app.window_added.connect ((window) => { window.set_decorated (false); });
        return app.run(args);''','Text through fontconfig and FreeType, not DirectWrite; opaque window, popovers and tooltips (no DWM alpha).')
    revise('src/mangojuice.vala','''        // Windows Game Manager -- deploy/remove proxy dxgi.dll per game
        var game_manager = new GameManager ();
        var game_manager_scrolled = create_scrolled_window (game_manager);
        add_view_to_stack (game_manager_scrolled, "games_box", _("Games"),
                          "applications-games-symbolic");
''','''        // OrbisDesk: no Games page. It starts a standalone MangoHud.exe on a running game and registers
        // the layer in HKLM through reg.exe; OrbisDesk loads MangoHud as an implicit layer already.
''','No Games page (standalone MangoHud.exe and HKLM layer registration do not apply).')
    # The Windows fork stubs vkcube and glxgears out (Linux test tools), so every start showed "vkcube and glxgears not
    # found" and no test button. OrbisDesk ships both in C:\orbis (tools/make-start-menu.py's Graphics Tools); the test
    # button starts one of them as a guest with MangoHud on it. Whether one is running is not tracked (no restart on save).
    revise('src/mangojuice.vala','''    void restart_vkcube () {
        // vkcube is not available on Windows.
    }

    void restart_glxgears () {
        // glxgears is not available on Windows.
    }''','''    // OrbisDesk: its own test programs (tools/make-start-menu.py)
    const string ORBIS_VKCUBE = "C:\\\\orbis\\\\vkcube.exe";
    const string ORBIS_GLXGEARS = "C:\\\\orbis\\\\glxgears.exe";

    [CCode (cname = "WinExec", cheader_filename = "windows.h")]
    static extern uint win_exec (string command, uint show);

    void start_orbis_tool (string path) {
        uint result = win_exec ("\\"" + path + "\\"", 1 /* SW_SHOWNORMAL */);
        if (result <= 31) stderr.printf ("Could not start %s: %u\\n", path, result);
    }

    void restart_vkcube () {
        start_orbis_tool (ORBIS_VKCUBE);
    }

    void restart_glxgears () {
        start_orbis_tool (ORBIS_GLXGEARS);
    }''','vkcube and glxgears: OrbisDesk\'s own, started by the test button.')
    revise('src/mangojuice.vala','''    public bool is_vkcube_available () {
        // vkcube is a Linux Vulkan test tool; not available on Windows.
        return false;
    }''','''    public bool is_vkcube_available () {
        return FileUtils.test (ORBIS_VKCUBE, FileTest.EXISTS);
    }''','vkcube is available when OrbisDesk\'s is present.')
    revise('src/mangojuice.vala','''    public bool is_glxgears_available () {
        // glxgears is a Linux OpenGL test tool; not available on Windows.
        return false;
    }''','''    public bool is_glxgears_available () {
        return FileUtils.test (ORBIS_GLXGEARS, FileTest.EXISTS);
    }''','glxgears is available when OrbisDesk\'s is present.')
    # The fork's run_test only made sure MangoHud.conf exists (d8: the Test button opened nothing)
    revise('src/mangojuice.vala','''                Idle.add (() => {
                    test_button_pressed = true;
                    return false;
                });''','''                Idle.add (() => {
                    test_button_pressed = true;
                    if (is_vkcube_available ()) restart_vkcube ();
                    else if (is_glxgears_available ()) restart_glxgears ();
                    return false;
                });''','The Test button starts OrbisDesk\'s vkcube or glxgears.')
    # d8: with no shadow the popovers still had a transparent band around them (the arrow's and the contents'
    # margin), black under Wine. The popovers have no arrow, and their contents no margin (CSS above)
    revise('src/mangojuice.vala','''        menu_button.set_menu_model (menu_model);
''','''        menu_button.set_menu_model (menu_model);
        menu_button.get_popover ().set_has_arrow (false);
''','The main menu has no arrow (no transparent band under Wine).')
    revise('src/mangojuice.vala','''        popover.set_has_arrow(true);
        popover.set_parent(font_button);''','''        popover.set_has_arrow(false);
        popover.set_parent(font_button);''','The font popover has no arrow.')
    revise('src/dialog.vala','''        var popover = new Gtk.Popover();
        var popover_label''','''        var popover = new Gtk.Popover();
        popover.set_has_arrow(false);
        var popover_label''','The presets hint popover has no arrow.')
    (work/'gen').mkdir();(work/'obj').mkdir()
    vala=sorted(str(p.relative_to(work)) for p in src.rglob('*.vala'))
    run([str(tools/'usr/bin/valac-0.56'),'-C','-d','gen','--vapidir',str(usr/'share/vala-0.56/vapi'),
         '--vapidir',str(usr/'share/vala/vapi'),'--vapidir','src','--pkg','libadwaita-1','--pkg','gee-0.8',
         '--pkg','gtk4','--pkg','gio-2.0','--pkg','config','--gresources','data/gresource.xml',*vala],cwd=work,env=env)
    (work/'obj/config.h').write_text('#define GETTEXT_PACKAGE "mangojuice"\n#define GNOMELOCALEDIR "share/locale"\n'
                                      '#define VERSION "0.8.9"\n#define IS_DEVEL 0\n')
    run(['glib-compile-resources','--generate-source','--target=../obj/resources.c','gresource.xml'],cwd=work/'data')
    pkg_env=dict(os.environ,PKG_CONFIG_SYSROOT_DIR=str(sysroot),PKG_CONFIG_LIBDIR=str(usr/'lib/pkgconfig'))
    modules=['libadwaita-1','gee-0.8','gtk4','gio-2.0']
    cflags=run(['pkg-config','--cflags',*modules],env=pkg_env).split()
    libs=run(['pkg-config','--libs',*modules],env=pkg_env).split()
    flags=['-O2','-w','-DGETTEXT_PACKAGE="mangojuice"','-Iobj','-ffile-prefix-map=%s=.'%work]
    objects=[]
    for c in sorted((work/'gen').rglob('*.c'))+[work/'obj/resources.c']:
        o='obj/'+c.stem+'.o';run([str(clang),*flags,*cflags,'-c',str(c.relative_to(work)),'-o',o],cwd=work);objects.append(o)
    links=[]
    for name in ('a','b'):
        (work/name).mkdir();command=[str(clang),'-mwindows','-s','-Wl,--no-insert-timestamp','-o',name+'/mangojuice.exe',*objects,*libs]
        run(command,cwd=work);links.append(work/name/'mangojuice.exe')
    if sha(links[0])!=sha(links[1]):raise SystemExit('the two links differ: the build is not reproducible')
    # the program's DLL closure from the MSYS2 tree; the rest must come from Wine
    bin_dir=usr/'bin';local={p.name.lower():p for p in bin_dir.glob('*.dll')}
    def imports(path):
        return [l.split(':',1)[1].strip().lower() for l in run([str(objdump),'-p',str(path)]).splitlines() if 'DLL Name:' in l]
    shipped={};system=set();todo=[links[0]]
    while todo:
        for dll in imports(todo.pop()):
            if dll in local and dll not in NOT_SHIPPED:
                if dll not in shipped:shipped[dll]=local[dll];todo.append(local[dll])
            else:system.add(dll)
    # out/: program, DLLs, GTK data, licences, icon
    if out.exists():shutil.rmtree(out)
    app=out/'MangoJuice';(app/'bin').mkdir(parents=True)
    shutil.copyfile(links[0],app/'bin/mangojuice.exe')
    for dll in shipped.values():shutil.copyfile(dll,app/'bin'/dll.name)
    schemas=app/'share/glib-2.0/schemas';schemas.mkdir(parents=True)
    for xml in sorted((usr/'share/glib-2.0/schemas').glob('*.gschema.xml')):shutil.copyfile(xml,schemas/xml.name)
    run(['glib-compile-schemas',str(schemas)])
    for theme in ('hicolor','Adwaita'):shutil.copytree(usr/'share/icons'/theme,app/'share/icons'/theme)
    # fontconfig reads <bin>/../etc/fonts/fonts.conf: MSYS2's, which scans C:\windows\Fonts and caches in
    # %LOCALAPPDATA%\fontconfig. The console has Tahoma and Marlett only; local.conf names Tahoma for GTK's families.
    shutil.copytree(usr/'etc/fonts',app/'etc/fonts')
    (app/'etc/fonts/local.conf').write_text('<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        '<!-- OrbisDesk (tools/build-mangojuice-hw.py): the console\'s UI font for every family GTK asks for -->\n<fontconfig>\n'
        +''.join('  <alias binding="same"><family>%s</family><prefer><family>Tahoma</family></prefer></alias>\n'%family
                 for family in ('sans-serif','serif','monospace','system-ui','Adwaita Sans','Cantarell','Segoe UI'))
        +'</fontconfig>\n')
    apps=app/'share/icons/hicolor/scalable/apps'
    for svg in sorted((work/'data/assets/icons').glob('*.svg'))+[work/'data/icons/hicolor/scalable/apps/io.github.radiolamp.mangojuice.svg']:
        shutil.copyfile(svg,apps/svg.name)
    licences=app/'licenses';(licences/'mangojuice').mkdir(parents=True)
    shutil.copyfile(SOURCE/'LICENSE',licences/'mangojuice/LICENSE')
    packages_shipped=sorted({owner['ucrt64/bin/'+dll] for dll in shipped}|{owner[k] for k in owner
                             if k.startswith(('ucrt64/share/icons/','ucrt64/share/glib-2.0/schemas/','ucrt64/etc/fonts/'))})
    standard_licence=[]
    for package in packages_shipped:
        folder=usr/'share/licenses'/package[len(PREFIX):]
        if folder.is_dir():shutil.copytree(folder,licences/folder.name)
        else:standard_licence.append(package)
    # packages that ship no licence files (GStreamer's, LGPL-2.1-or-later): the standard text is LICENSES/LGPL-2.1.txt
    shutil.copyfile(ROOT/'LICENSES/LGPL-2.1.txt',licences/'LGPL-2.1.txt');shutil.copyfile(ROOT/'LICENSES/GPL-3.0.txt',licences/'GPL-3.0.txt')
    svg=work/'data/icons/hicolor/scalable/apps/io.github.radiolamp.mangojuice.svg';images=[]
    for size in SIZES:
        png=work/('icon-%d.png'%size)
        run([str(tools/'usr/bin/rsvg-convert'),'-w',str(size),'-h',str(size),'-o',str(png),str(svg)],env=env)
        images.append((size,png_rgba(png.read_bytes())))
        shutil.copyfile(png,out/png.name)  # previews of the small sizes
    (app/'mangojuice.ico').write_bytes(ico(images))
    files={p.relative_to(out).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(app.rglob('*')) if p.is_file()}
    manifest={'schema_version':1,'program':'MangoJuice/bin/mangojuice.exe','target':'C:\\Program Files\\MangoJuice',
              'source':pins['source'],'lock_sha256':sha(LOCK),'builder_sha256':sha(pathlib.Path(__file__)),
              'revisions':revisions,'compiler':run([str(clang),'--version']).splitlines()[0],
              'reproducible':'two links identical','dlls':sorted(p.name for p in shipped.values()),
              'packages_shipped':packages_shipped,'packages_without_licence_files':standard_licence,'system_imports':sorted(system),'not_shipped':sorted(NOT_SHIPPED),
              'files':files,'bytes':sum(e['bytes'] for e in files.values()),
              'host_tools':{'glib-compile-resources':run(['glib-compile-resources','--version']).strip(),
                            'pkg-config':run(['pkg-config','--version']).strip()}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=1)+'\n')
    print(json.dumps({'files':len(files),'MiB':round(manifest['bytes']/2**20,1),'dlls':len(shipped),
                      'exe_sha256':files['MangoJuice/bin/mangojuice.exe']['sha256'],'system_imports':len(system)}))

parser=argparse.ArgumentParser()
parser.add_argument('--fetch',action='store_true',help='download the pinned inputs that are missing, then build')
parser.add_argument('--lock',action='store_true',help='re-resolve the pins from MSYS2 and Ubuntu (no build)')
parser.add_argument('--keep-work',action='store_true',help='keep build/mangojuice-hw (about 1 GiB) after a build')
args=parser.parse_args()
if args.lock:lock()
else:
    pins=json.loads(LOCK.read_text())
    if args.fetch:fetch(pins)
    build(pins)
    if not args.keep_work:shutil.rmtree(work)
