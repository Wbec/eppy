"""idd comments have gaps in them.
With \note fields as indicated
This code fills those gaps
see: SCHEDULE:DAY:LIST as an example"""

# TODO : need to factor this code. Then make it work for the objects I skipped below.

# idd might look like this
# <snip>
# / field varA 1
# / field varB 1
# / field varC 1
# / field varA 2
# / field varB 2
# / field varC 2
# / above pattern continues
# - 
# find objects where the fields are not named
# do the following only for those objects
# find the first field that has an integer. This is a repeating field
# gather the repeating field names (without the integer)
# generate all the repeating fields for all variables



import sys
from pprint import pprint
sys.path.append('../EPlusInputcode')
from EPlusCode.EPlusInterfaceFunctions import readidf

import bunchhelpers

# read code
iddfile = "../iddfiles/Energy+V6_0.idd"
fname = "./walls.idf" # small file with only surfaces
data, commdct = readidf.readdatacommdct(fname, iddfile=iddfile)
commdct = bunchhelpers.cleancommdct(commdct)

dt = data.dt
dtls = data.dtls
# find objects where all the fields are not named
gkeys = [dtls[i] for i in range(len(dtls)) if commdct[i].count({}) > 2]

# operatie on those fields
for key_txt in gkeys:
    if key_txt in ['MATERIALPROPERTY:GLAZINGSPECTRALDATA', 
                    'GROUNDHEATTRANSFER:SLAB:XFACE',
                    'GROUNDHEATTRANSFER:SLAB:YFACE',
                    'GROUNDHEATTRANSFER:SLAB:ZFACE',
                    'GROUNDHEATTRANSFER:BASEMENT:XFACE',
                    'GROUNDHEATTRANSFER:BASEMENT:YFACE',
                    'GROUNDHEATTRANSFER:BASEMENT:ZFACE',
                    'TABLE:MULTIVARIABLELOOKUP']: # the gaps are hard to fill 
                                                # here. May not be necessary,
                                                # as these may not be used.
        continue
    print key_txt
    # for a function, pass comm as a variable
    key_i = dtls.index(key_txt.upper())
    comm = commdct[key_i]



    # get all fields
    fields = []
    for field in comm:
        if field.has_key('field'):
            fields.append(field)

    # get repeating field names
    fnames = [field['field'][0] for field in fields]
    fnames = [bunchhelpers.onlylegalchar(fname) for fname in fnames]
    fnames = [fname for fname in fnames if bunchhelpers.intinlist(fname.split())]
    fnames = [(bunchhelpers.replaceint(fname), None) for fname in fnames]
    dct = dict(fnames)
    repnames = fnames[:len(dct.keys())]
    first = repnames[0][0] % (1, )

    # get all comments of the first repeating field names
    firstnames = [repname[0] % (1, ) for repname in repnames]
    fcomments = [field for field in fields if bunchhelpers.onlylegalchar(field['field'][0]) in firstnames]
    fcomments = [dict(fcomment) for fcomment in fcomments]
    for cm in fcomments:
        fld = cm['field'][0]
        fld = bunchhelpers.onlylegalchar(fld)
        fld = bunchhelpers.replaceint(fld)
        cm['field'] = [fld]

    for i, cm in enumerate(comm[1:]):
        thefield = cm['field'][0]
        thefield = bunchhelpers.onlylegalchar(thefield)
        if thefield == first:
            break
    first_i = i + 1

    newfields = []
    for i in range(1, len(comm[first_i:]) / len(repnames) + 1):
        for fcomment in fcomments:
            nfcomment = dict(fcomment)
            fld = nfcomment['field'][0]
            fld = fld % (i, )
            nfcomment['field'] = [fld]
            newfields.append(nfcomment)

    for i, cm in enumerate(comm):
        if i < first_i:
            continue
        else:
            afield = newfields.pop(0)
            comm[i] = afield
     
    # for i in range(10):
    #     pprint(comm[:2])