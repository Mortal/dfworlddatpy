import sys
import struct

cp437 = (
    " ☺☻♥♦♣♠•◘○◙♂♀♪♫☼"
    "►◄↕‼¶§▬↨↑↓→←∟↔▲▼"
    " !\"#$%&'()*+,-./"
    "0123456789:;<=>?"
    "@ABCDEFGHIJKLMNO"
    "PQRSTUVWXYZ[\\]^_"
    "`abcdefghijklmno"
    "pqrstuvwxyz{|}~⌂"
    "ÇüéâäàåçêëèïîìÄÅ"
    "ÉæÆôöòûùÿÖÜ¢£¥₧ƒ"
    "áíóúñÑªº¿⌐¬½¼¡«»"
    "░▒▓│┤╡╢╖╕╣║╗╝╜╛┐"
    "└┴┬├─┼╞╟╚╔╩╦╠═╬╧"
    "╨╤╥╙╘╒╓╫╪┘┌█▄▌▌▄"
    "αßΓπΣσµτΦΘΩδ∞φε∩"
    "≡±≥≤⌠⌡÷≈°∙·√ⁿ²■ ")

def dfdecode(b):
    return ''.join(cp437[c] for c in b)

def hexdump(pos, b):
    line_length = 16
    for offs in range(0, len(b), line_length):
        line = b[offs:offs+line_length]
        yield '%08x  %s %s' % (pos + offs,
                ' '.join('%02x' % octet for octet in line).ljust(3*line_length),
                dfdecode(line),
                )

class RecallFile(object):
    def __init__(self, fp):
        self._fp = fp
        self._buffers = []

    def push(self):
        self._buffers.append(b'')

    def pop(self):
        s = self._buffers.pop()
        if self._buffers:
            self._buffers[-1] += s
        return s

    def read(self, *args, **kwargs):
        s = self._fp.read(*args, **kwargs)
        if self._buffers:
            self._buffers[-1] += s
        return s

    def seek(self, n):
        return self._fp.seek(n)

    def tell(self):
        return self._fp.tell()

class Format(object):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def skip(self, fp):
        for i in self.dump(fp):
            pass

class Atom(Format):
    def dump(self, fp):
        yield str(self.parse(fp))

def stats(a):
    if not a:
        return 'Empty'
    if len(a) == 1:
        return 'Singleton'
    s = sorted(a)
    distinct = 1
    simple_inversions = 0
    for i in range(1, len(s)):
        if s[i-1] != s[i]:
            distinct += 1
        if s[i-1] > s[i]:
            simple_inversions += 1
    return ('%d items in range [%s, %s], %s distinct, %s simple inversions'
            % (len(a), s[0], s[-1],
                'all' if distinct == len(a) else distinct,
                simple_inversions))

class MultiFormat(Format):
    def parse(self, fp):
        return [fmt.parse(fp) for fmt in self.get_formats(fp)]

    def skip(self, fp):
        for fmt in self.get_formats(fp):
            fmt.skip(fp)

    def dump(self, fp):
        if self.kwargs.get('short', False):
            pos = fp.tell()
            fp.push()
            items = self.parse(fp)
            yield from hexdump(pos, fp.pop())
            if len(items) > 1:
                yield stats(items)
            yield '[%s]' % ', '.join(str(each) for each in items)

        else:
            for i, fmt in enumerate(self.get_formats(fp)):
                indent = self.indent_fmt % i
                pos = fp.tell()
                try:
                    for line in fmt.dump(fp):
                        yield '%s%s' % (indent, line)
                except KeyboardInterrupt:
                    raise
                except SystemExit:
                    raise
                except:
                    yield '%s%s' % (indent,
                            'Exception raised when parsing at 0x%08x:' % pos)
                    fp.seek(pos)
                    yield from Bytes(0x100).dump(fp)
                    raise
                #yield 'Length: %d' % (fp.tell() - pos)

class Skip(Format):
    def parse(self, fp):
        self.args[0].parse(fp)

    def dump(self, fp):
        self.args[0].skip(fp)
        yield from []

class Struct(Atom):
    def __init__(self, *args, **kwargs):
        super(Struct, self).__init__(*args, **kwargs)
        self._struct = struct.Struct(self.format)

    def parse(self, fp):
        return self._struct.unpack(fp.read(self._struct.size))[0]

class Byte(Struct):
    format = '<b'

class Short(Struct):
    format = '<h'

class Int(Struct):
    format = '<i'

class Pstring(Format):
    def parse(self, fp):
        n = Short().parse(fp)
        if n < 0:
            raise Exception("Pstring has negative length %d" % n)
        return fp.read(n)

    def dump(self, fp):
        yield repr(self.parse(fp))

class DFstring(Format):
    def parse(self, fp):
        n = Short().parse(fp)
        if n < 0:
            raise Exception("DFstring has negative length: %d" % n)
        if n > 80:
            raise Exception("DFstring is longer than 80: %d" % n)
        return fp.read(n).decode('cp437')

    def dump(self, fp):
        yield repr(self.parse(fp))

class Tuple(MultiFormat):
    indent_fmt = '.%d '
    def get_formats(self, fp):
        return self.args[0]

class NamedTuple(Format):
    def parse(self, fp):
        for k in self.args[0]:
            yield (k, self.args[1].parse(fp))

    def dump(self, fp):
        for k in self.args[0]:
            yield "%s:" % k
            yield from self.args[1].dump(fp)

    def skip(self, fp):
        for i in range(len(self.args[0])):
            self.args[1].skip(fp)

class Array(MultiFormat):
    indent_fmt = '[%d] '
    def get_formats(self, fp):
        return int(self.args[0]) * (self.args[1],)

class VectorInt(MultiFormat):
    indent_fmt = '[%d] '
    def get_formats(self, fp):
        n = Int().parse(fp)
        if n > 0x10000:
            raise Exception("Vector too large (0x%x)" % n)
        return n * (self.args[0],)

class Output(Format):
    def parse(self, fp):
        pass

    def dump(self, fp):
        yield from [self.args[0]]

    def skip(self, fp):
        pass

class Expect(Format):
    def parse(self, fp):
        got = self.args[0].parse(fp)
        expected = self.args[1]
        if got != expected:
            raise Exception("Expected:\n%r\nGot:\n%r"
                    % (expected, got))

    def dump(self, fp):
        self.parse(fp)
        yield from []

class ExpectBytes(Format):
    def parse(self, fp):
        got = fp.read(len(self.args[0]))
        expected = self.args[0]
        if got != expected:
            raise Exception("Expected:\n%s\nGot:\n%s"
                    % ('\n'.join(hexdump(0, expected)),
                        '\n'.join(hexdump(0, got))))

    def dump(self, fp):
        self.parse(fp)
        yield from []

class ExpectZeros(Format):
    def parse(self, fp):
        n = int(self.args[0])
        got = Bytes(n).parse(fp)
        expected = b'\0' * n
        if got != expected:
            raise Exception("Expected %d zero bytes, got:\n%s"
                    % (n, '\n'.join(hexdump(0, got))))

    def dump(self, fp):
        self.parse(fp)
        yield from []

class Bytes(Atom):
    def parse(self, fp):
        return fp.read(self.args[0])

    def dump(self, fp):
        pos = fp.tell()
        b = self.parse(fp)
        yield from hexdump(pos, b)

class Rest(Format):
    def parse(self, fp):
        return fp.read()

    def dump(self, fp):
        pos = fp.tell()
        yield from hexdump(pos, fp.read())

class Break(Format):
    def parse(self, fp):
        return None

    def dump(self, fp):
        yield 'Press a key to continue...'
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            raise SystemExit()
        if not line:
            raise SystemExit()

class Parser(object):
    def __init__(self, fp, dest):
        self._fp = fp
        self._dest = dest
        self._dump = True

    def no_dump(self):
        self._dump = False

    def do_dump(self):
        self._dump = True

    def output(self, fmt, *args, dump=False):
        if self._dump or not dump:
            self._dest.write("%s\n" % (fmt % args))
            self._dest.flush()

    def read(self, n):
        return self._fp.read(n)

    def skip(self, n):
        self.read(n)

    def tell(self):
        return self._fp.tell()

    def parse_struct(self, s):
        return s.unpack(self.read(s.size))

    def parse_short(self):
        return self.parse_struct(struct.Struct('<h'))[0]

    def parse_int(self):
        return self.parse_struct(struct.Struct('<i'))[0]

    def parse_pstring(self):
        n = self.parse_short()
        return self.read(n)

    def expect(self, expected, got):
        if got != expected:
            raise Exception("Got %r, expected %r" % (got, expected))

    def expect_pstring(self, expected):
        self.expect(expected, self.parse_pstring())

    def expect_int(self, expected):
        self.expect(expected, self.parse_int())

    def expect_short(self, expected):
        self.expect(expected, self.parse_short())

    def expect_bytes(self, expected):
        self.expect(expected, self.read(len(expected)))

    def array_int(self, name, limit=0x10000):
        count = self.parse_int()
        if 0 <= count < limit:
            self.output("%s count = %s", name, count)
            return range(count)
        else:
            raise Exception("Count for %r is out of range [0, %d): %d"
                    % (name, limit, count))

    def array_short(self, name):
        count = self.parse_short()
        self.output("%s count (short) = %s", name, count)
        return range(count)

    def dump_bytes(self, n):
        self.output("(0x%x) [%s]", self.tell(), ' '.join('%02x' % i for i in self.read(n)), dump=True)

    def dump_pstring(self):
        self.output("(0x%x) %s", self.tell(), self.parse_pstring().decode(), dump=True)

    def dump_int(self):
        self.output("(int 0x%x) %s", self.tell(), self.parse_int(), dump=True)

    def dump_short(self):
        self.output("(short 0x%x) %s", self.tell(), self.parse_short(), dump=True)

def make_tuple(*args):
    return Tuple(args)

def make_array(n, *args):
    return Array(n, Tuple(args))

vector_of_short = VectorInt(Short(), short=True)
vector_of_int = VectorInt(Int(), short=True)
vector_of_byte = VectorInt(Byte(), short=True)

def skip(do_skip, *args):
    if do_skip:
        return Skip(Tuple(args))
    else:
        return Tuple(args)

subterranean_animal_peoples = make_tuple(
    #Expect(Pstring(), b'SUBTERRANEAN_ANIMAL_PEOPLES'),
    Expect(Short(), 0x19),
    Expect(Short(), 0x4b),
    Int(), # 1, 2, 3, ...
    ExpectZeros(3),
    Short(), # 524, 526, 517, 528, 529, 530, 511, 529
    skip(True,
        make_array(18,
            vector_of_int,
            vector_of_short,
        ),
        vector_of_int,
        vector_of_int,
        vector_of_short,
        vector_of_int,
        vector_of_short,
        Int(),
        Int(),
        make_array(10,
            vector_of_int,
            vector_of_short,
        ),
        make_array(2,
            vector_of_short,
            vector_of_int,
        ),
        Expect(Int(), 0),
        make_array(9,
            vector_of_short,
            vector_of_int,
        ),
        Bytes(0x12),
        vector_of_int,
        make_array(2,
            vector_of_short,
            vector_of_int,
        ),
        Bytes(14),
        make_array(15,
            vector_of_short,
            vector_of_int,
        ),
        make_array(2,
            vector_of_int,
            vector_of_short,
        ),
    ),
    Expect(Int(), 1),
    Short(),
    Bytes(256),
    Int(),
)

mountain = make_tuple(
    #Expect(Pstring(), b'MOUNTAIN'),
    Short(),
    Short(),
    Int(),
    Bytes(0x3d),
    make_array(18,
        vector_of_short,
        vector_of_int,
    ),
    make_array(2,
        vector_of_int,
        vector_of_short,
    ),
    make_array(2,
        vector_of_short,
        vector_of_int,
    ),
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_int,
    make_array(7,
        vector_of_int,
        vector_of_short,
    ),
    vector_of_short,
    vector_of_int,
    vector_of_int,
    vector_of_int,
    vector_of_int,
    make_array(9,
        vector_of_short,
        vector_of_int,
    ),
    Bytes(0x12),
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    vector_of_short,
    make_array(10,
        vector_of_short,
        vector_of_int,
    ),

    VectorInt(make_tuple(Short(), Int(), Short())),
    Bytes(16),
    vector_of_int,
    vector_of_int,
    vector_of_int,
    vector_of_short,
    Bytes(14*16-2),
    Bytes(14),
    vector_of_int,
    vector_of_byte,
    vector_of_int,

    vector_of_int,
)

class DFNamedSections(Format):
    def parse(self, fp):
        while True:
            n = Pstring().parse(fp)
            if n == b'SUBTERRANEAN_ANIMAL_PEOPLES':
                yield subterranean_animal_peoples.parse(fp)
            elif n == b'MOUNTAIN':
                yield mountain.parse(fp)
                return

    def dump(self, fp):
        i = 0
        while True:
            n = Pstring().parse(fp)
            if n == b'SUBTERRANEAN_ANIMAL_PEOPLES':
                for line in subterranean_animal_peoples.dump(fp):
                    yield '#%d %s' % (i, line)
                i = i + 1
            elif n == b'MOUNTAIN':
                yield 'Done processing SUBTERRANEAN_ANIMAL_PEOPLES'
                yield from mountain.dump(fp)
                return

world_header = make_tuple(
    Short(),
    Array(16, Int(), short=True),
    Bytes(104),
    # World name
    DFstring(),
)

world_dat = make_tuple(
    skip(True, world_header),
    skip(True,
        # Generated raw blocks
        NamedTuple(
            ("inorganic_generated", "unknown layer",
                "creature_layer", "interaction_layer"),
            VectorInt(
                # Raw block
                VectorInt(
                    # Raw
                    Pstring()
                ),
            ),
        ),
        # Tag blocks
        NamedTuple("""
            Material Plant Body1 Body2 Creature Item Workshop EntityCiv Word
            NameTag MainCiv Color1 Shape Color2 Reaction MaterialTemplate
            TissueTemplate BodyDetailPlan CreatureVariation Interaction
            """.split(),
            # Tag block
            VectorInt(
                # Tag
                Pstring(),
            ),
        ),
        VectorInt(Tuple((Int(), Int())), short=True),
        Expect(Int(), 0),
        vector_of_int,
        vector_of_int,
    ),
    skip(True,
        vector_of_int,
        ExpectZeros(20),
        vector_of_int,
        vector_of_int,
        VectorInt(Int()),
    ),
    #Bytes(18),
    Bytes(0x100),
    Break(),
    DFNamedSections(),
    Output('Begin processing MONARCH, GENERAL et al'),
    Bytes(0x84),
    Expect(DFstring(), 'MONARCH'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x6f),
    Expect(DFstring(), 'GENERAL'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    Expect(DFstring(), 'LIEUTENANT'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    Expect(DFstring(), 'CAPTAIN'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x6d),
    Expect(DFstring(), 'OUTPOST_LIAISON'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    Expect(DFstring(), 'DIPLOMAT'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7b),
    Expect(DFstring(), 'MILITIA_COMMANDER'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7F),
    Expect(DFstring(), 'MILITIA_CAPTAIN'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x6D),
    Expect(DFstring(), 'SHERIFF'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7F),
    Expect(DFstring(), 'CAPTAIN_OF_THE_GUARD'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x75),
    Expect(DFstring(), 'EXPEDITION_LEADER'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x6F),
    Expect(DFstring(), 'MAYOR'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x6F),
    Expect(DFstring(), 'MANAGER'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7F),
    Expect(DFstring(), 'CHIEF_MEDICAL_DWARF'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7F),
    Expect(DFstring(), 'BROKER'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7F),
    Expect(DFstring(), 'BOOKKEEPER'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x7F),
    Expect(DFstring(), 'DUKE'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    Expect(DFstring(), 'COUNT'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    Expect(DFstring(), 'BARON'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    Expect(DFstring(), 'CHAMPION'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x87),
    Expect(DFstring(), 'HAMMERER'),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x83),
    Expect(DFstring(), 'FORCED_ADMINISTRATOR'),
    Bytes(28),
    make_array(16, DFstring()),

    #Output(75 * '='),
    #Output("Rest:"),
    #Rest()
)



class WorldDatParser(Parser):
    def dump(self):
        self.no_dump()
        self.dump_world_header()
        self.dump_world_name()
        self.dump_generated_raw_blocks()
        self.dump_tag_blocks()

        self.do_dump()
        self.dump_int()
        self.dump_int()
        for each in self.array_int("Numbers"):
            self.dump_int()
        for each in self.array_int("Numbers"):
            self.dump_int()
        self.skip(58)
        for each in range(11):
            self.expect_pstring(b'SUBTERRANEAN_ANIMAL_PEOPLES')
            self.expect_short(0x19)
            self.expect_short(0x4b)
            number = self.parse_int()
            self.expect_bytes(b'\0\0\0')
            self.dump_short()
            for each in range(19):
                for each in self.array_int('Ints'):
                    self.dump_int()
                for each in self.array_int('Shorts'):
                    self.dump_short()
            self.expect_int(0)
            for each in self.array_int('Ints'):
                self.dump_int()
            for each in self.array_int('Shorts'):
                self.dump_short()
            self.output("Point 1")
            self.dump_int()
            self.dump_int()
            for each in range(11):
                for each in self.array_int('Ints'):
                    self.dump_int()
                for each in self.array_int('Shorts'):
                    self.dump_short()
            self.output("Point 2")
            for each in range(2):
                for each in self.array_int('Shorts'):
                    self.dump_short()
                for each in self.array_int('Ints'):
                    self.dump_int()
            self.expect_int(0)
            self.output("Point 3")
            for each in range(9):
                for each in self.array_int('Shorts'):
                    self.dump_short()
                for each in self.array_int('Ints'):
                    self.dump_int()

            self.dump_bytes(0x12)
            self.output("Point 4")
            for each in self.array_int('Ints'):
                self.dump_int()
            for each in range(2):
                for each in self.array_int('Shorts'):
                    self.dump_short()
                for each in self.array_int('Ints'):
                    self.dump_int()
            self.dump_bytes(14)
            self.output("Point 5")
            for each in range(15):
                for each in self.array_int('Shorts'):
                    self.dump_short()
                for each in self.array_int('Ints'):
                    self.dump_int()
            for each in range(2):
                for each in self.array_int('Ints'):
                    self.dump_int()
                for each in self.array_int('Shorts'):
                    self.dump_short()

            self.expect_int(1)
            self.dump_short()
            #n = self.parse_short()
            self.dump_bytes(260)

        #rest = self._fp.read()
        #parts = rest.split(b'\x1b\x00SUBTERRANEAN_ANIMAL_PEOPLES')
        #self.output("Part lengths: %s", [len(p) for p in parts])
        #i = 1
        #for part in parts[1:-1]:
        #    with open('subt%02d' % i, 'wb') as fp:
        #        fp.write(part)
        #    i = i + 1

    def dump_generated_raw_blocks(self):
        kinds = ("inorganic_generated", "unknown layer", "creature_layer",
                "interaction_layer")
        for kind in kinds:
            self.output("Generated raw block: %s", kind)
            for each in self.array_int("Raw block"):
                for each in self.array_int("Raw"):
                    self.dump_pstring()

    def dump_world_header(self):
        version = self.parse_short()
        self.skip(168)
        self.output("Version %s", version)

    def dump_world_name(self):
        world_name = self.parse_pstring()
        self.output("World name length: %s", len(world_name))
        self.output("World name: %s", world_name.decode('CP437'))

    def dump_tag_blocks(self):
        kinds = """
            Material Plant Body1 Body2 Creature Item Workshop EntityCiv Word
            NameTag MainCiv Color1 Shape Color2 Reaction MaterialTemplate
            TissueTemplate BodyDetailPlan CreatureVariation Interaction
            """.split()
        for kind in kinds:
            self.output("Tag block: %s", kind)
            for each in self.array_int("Tag"):
                self.dump_pstring()

def main():
    world_dat_path = sys.argv[1] if len(sys.argv) > 1 else 'world.dat'
    with open(world_dat_path, 'rb') as world_dat_fp:
        #world_dat = WorldDatParser(world_dat_fp, sys.stdout)
        #world_dat.dump()
        for line in world_dat.dump(RecallFile(world_dat_fp)):
            print(line)
        #for line in world_header.dump(RecallFile(world_dat_fp)):
        #    print(line)

if __name__ == '__main__':
    main()
