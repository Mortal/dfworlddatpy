import sys
import struct

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
            for each in range(20):
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
        world_dat = WorldDatParser(world_dat_fp, sys.stdout)
        world_dat.dump()

if __name__ == '__main__':
    main()
