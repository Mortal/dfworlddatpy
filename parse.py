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

    def tell(self):
        return self._fp.tell()

class Format(object):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

class Atom(Format):
    def dump(self, fp):
        yield str(self.parse(fp))

class MultiFormat(Format):
    def parse(self, fp):
        for fmt in self.get_formats(fp):
            yield fmt.parse(fp)

    def dump(self, fp):
        if self.kwargs.get('short', False):
            pos = fp.tell()
            fp.push()
            items = [str(fmt.parse(fp)) for fmt in self.get_formats(fp)]
            yield from hexdump(pos, fp.pop())
            yield '[%s]' % ', '.join(items)

        else:
            for i, fmt in enumerate(self.get_formats(fp)):
                indent = self.indent_fmt % i
                for line in fmt.dump(fp):
                    yield '%s%s' % (indent, line)

class Skip(Format):
    def parse(self, fp):
        self.args[0].parse(fp)

    def dump(self, fp):
        for line in self.args[0].dump(fp):
            pass
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
        return fp.read(n)

    def dump(self, fp):
        yield repr(self.parse(fp))

class DFstring(Format):
    def parse(self, fp):
        n = Short().parse(fp)
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

class Array(MultiFormat):
    indent_fmt = '[%d] '
    def get_formats(self, fp):
        return int(self.args[0]) * (self.args[1],)

class VectorInt(MultiFormat):
    indent_fmt = '[%d] '
    def get_formats(self, fp):
        n = Int().parse(fp)
        return n * (self.args[0],)

class Output(Format):
    def parse(self, fp):
        pass

    def dump(self, fp):
        yield from [self.args[0]]

class Expect(Format):
    def parse(self, fp):
        got = self.args[0].parse(fp)
        expected = self.args[1]
        if got != expected:
            raise Exception("Expected %r, got %r" % (expected, got))

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

world_dat = make_tuple(
    # World header
    make_tuple(
        Short(),
        Skip(Bytes(168)),
    ),
    # World name
    DFstring(),
    skip(True,
        # Generated raw blocks
        NamedTuple(
            ("inorganic_generated", "unknown layer",
                "creature_layer", "interaction_layer"),
            make_tuple(
                VectorInt(
                    # Raw block
                    VectorInt(
                        # Raw
                        Pstring()
                    ),
                ),
            ),
        ),
        # Tag blocks
        NamedTuple("""
            Material Plant Body1 Body2 Creature Item Workshop EntityCiv Word
            NameTag MainCiv Color1 Shape Color2 Reaction MaterialTemplate
            TissueTemplate BodyDetailPlan CreatureVariation Interaction
            """.split(),
            make_tuple(
                # Tag block
                VectorInt(
                    # Tag
                    Pstring(),
                ),
            ),
        ),
        Int(),
        Int(),
        vector_of_int,
        vector_of_int,
    ),
    Bytes(58),
    skip(True,
        make_array(11,
            Expect(Pstring(), b'SUBTERRANEAN_ANIMAL_PEOPLES'),
            Expect(Short(), 0x19),
            Expect(Short(), 0x4b),
            Int(),
            Expect(Bytes(3), b'\0\0\0'),
            Short(),
            make_array(18,
                vector_of_int,
                vector_of_short,
            ),
            vector_of_int,
            vector_of_int,
            vector_of_short,
            vector_of_int,
            vector_of_short,
            Output("Point 1"),
            Int(),
            Int(),
            make_array(10,
                vector_of_int,
                vector_of_short,
            ),
            Output("Point 2"),
            make_array(2,
                vector_of_short,
                vector_of_int,
            ),
            Expect(Int(), 0),
            Output("Point 3"),
            make_array(9,
                vector_of_short,
                vector_of_int,
            ),
            Bytes(0x12),
            Output("Point 4"),
            vector_of_int,
            make_array(2,
                vector_of_short,
                vector_of_int,
            ),
            Bytes(14),
            Output("Point 5"),
            make_array(15,
                vector_of_short,
                vector_of_int,
            ),
            make_array(2,
                vector_of_int,
                vector_of_short,
            ),
            Expect(Int(), 1),
            Short(),
            Bytes(260),
        ),
    ),
    Pstring(),
    Bytes(0x45),
    skip(True,
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
        Bytes(0x24),
        vector_of_int,
        vector_of_int,
        vector_of_int,
        vector_of_short,
        vector_of_int,
        vector_of_short,
        Bytes(14*16-2),
        vector_of_int,
        vector_of_byte,
        vector_of_int,

        Bytes(0xB8),
        # MONARCH
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x6f),
        # GENERAL
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x77),
        # LIEUTENANT
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x77),
        # CAPTAIN
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x6d),
        # OUTPOST_LIAISON
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x77),
        # DIPLOMAT
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7b),
        # MILITIA_COMMANDER
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7F),
        # MILITIA_CAPTAIN
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x6D),
        # SHERIFF
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7F),
        # CAPTAIN_OF_THE_GUARD
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x75),
        # EXPEDITION_LEADER
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x6F),
        # MAYOR
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x6F),
        # MANAGER
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7F),
        # CHIEF_MEDICAL_DWARF
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7F),
        # BROKER
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7F),
        # BOOKKEEPER
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x7F),
        # DUKE
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x77),
        # COUNT
        DFstring(),
        Bytes(28),
        make_array(16, DFstring()),
        Bytes(0x77),
    ),
    # BARON
    DFstring(),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x77),
    # CHAMPION
    DFstring(),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x87),
    # HAMMERER
    DFstring(),
    Bytes(28),
    make_array(16, DFstring()),
    Bytes(0x83),
    # FORCED_ADMINISTRATORS
    DFstring(),
    Bytes(28),
    make_array(16, DFstring()),

    Output(75 * '='),
    Output("Rest:"),
    Rest()
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

if __name__ == '__main__':
    main()
