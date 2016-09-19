# Copyright (c) 2012 Santosh Philip
# =======================================================================
#  Distributed under the MIT License.
#  (See accompanying file LICENSE or copy at
#  http://opensource.org/licenses/MIT)
# =======================================================================
"""make plant loop snippets"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import copy

from eppy.bunchhelpers import sanitizefieldname

import eppy.bunch_subclass as bunch_subclass
import eppy.modeleditor as modeleditor


class WhichLoopError(Exception):
    pass


def makeplantloop(idf, loopname, sloop, dloop):
    """Make plant loop with pipe components.
    
    Parameters
    ----------
    idf : IDF object
        The IDF.
    loopname : str
        Name for the loop.
    sloop : list
        A list of names for each branch on the supply loop.
        Example: ['s_inlet', ['boiler', 'bypass'], 's_outlet]
    dloop : list
        A list of names for each branch on the loop.
        Example: ['d_inlet', ['zone1', 'zone2'], 'd_outlet]
    
    Returns
    -------
    EPBunch

    """
    return PlantLoop(idf, loopname, sloop, dloop)
#    return loop.makeloop()


def makecondenserloop(idf, loopname, sloop, dloop):
    """Make loop with pipe components

    Parameters
    ----------
    idf : IDF object
        The IDF.
    loopname : str
        Name for the loop.
    sloop : list
        A list of names for each branch on the supply loop.
        Example: ['s_inlet', ['tower', 'supply bypass'], 's_outlet]
    dloop : list
        A list of names for each branch on the loop.
        Example: ['d_inlet', ['chiller condenser', 'demand bypass'], 'd_outlet]
    
    Returns
    -------
    EPBunch

    """
    return  CondenserLoop(idf, loopname, sloop, dloop)
#    return loop.makeloop()


def makeairloop(idf, loopname, sloop, dloop):
    """Make an airloop with pipe components.
    Parameters
    ----------
    idf : IDF object
        The IDF.
    loopname : str
        Name for the loop.
    sloop : list
        A list of names for each branch on the supply loop.
        Example: ['s_inlet', ['oa sys'], 's_outlet]
    dloop : list
        A list of names for each branch on the loop.
        Example: ['d_inlet', ['zone1', 'zone2'], 'd_outlet]
    
    Returns
    -------
    EPBunch

    """
    # TODO: unit test
    return AirLoopHVAC(idf, loopname, sloop, dloop)
#    return loop.makeloop()


class Loop(object):
    
    def __init__(self, idf, loopname, sloop, dloop):
        self.idf = idf
        self.sloop = sloop
        self.dloop = dloop
        self.newloop = idf.newidfobject(self.looptype, loopname)
        self.loop = self.makeloop()
    
    @property
    def looptype(self):
        return type(self).__name__.upper()
    
    def makeloop(self):
        initialise_loop(self.newloop, self.loopfields)
        
        self.set_branchlists()        
        self.make_supply_branches()
        self.make_demand_branches()

        self.rename_endpoints()
        
        self.make_supply_connectorlists()
        self.make_demand_connectorlists()

        self.make_splitters_and_mixers()
    
        return self.newloop

    def rename_endpoints(self):
        rename_endpoints(
            self.idf, self.newloop, self.d_branches, self.s_branches)
    
    def make_supply_branches(self):
        supply_branchnames = flattencopy(self.sloop)
        for branchname in supply_branchnames:
            self.supply_branchlist.obj.append(branchname)
        # make a pipe branch for all supply branches in the loop
        supply_branches = [pipebranch(self.idf, branchname) 
                           for branchname in supply_branchnames]
        self.s_branches = supply_branches
        
    def make_demand_branches(self):
        # add demand branch names to the branchlist
        demand_branchnames = flattencopy(self.dloop)
        for branchname in demand_branchnames:
            self.demand_branchlist.obj.append(branchname)
        self.d_branches = demand_branchnames
    
    def make_splitters_and_mixers(self):
        supply_splitter = self.idf.newidfobject(
            "CONNECTOR:SPLITTER", 
            self.s_connlist.Connector_1_Name)
        supply_splitter.obj.extend([self.sloop[0]] + self.sloop[1])
        supply_mixer = self.idf.newidfobject(
            "CONNECTOR:MIXER", 
            self.s_connlist.Connector_2_Name)
        supply_mixer.obj.extend([self.sloop[-1]] + self.sloop[1])
    
        demand_splitter = self.idf.newidfobject(
            "CONNECTOR:SPLITTER", 
            self.d_connlist.Connector_1_Name)
        demand_splitter.obj.extend([self.dloop[0]] + self.dloop[1])
        demand_mixer = self.idf.newidfobject(
            "CONNECTOR:MIXER", 
            self.d_connlist.Connector_2_Name)
        demand_mixer.obj.extend([self.dloop[-1]] + self.dloop[1])
    
    def replacebranch(self, branch,
                      listofcomponents, fluid=None,
                      debugsave=False,
                      testing=None):
        """It will replace the components in the branch with components in
        listofcomponents"""
        if fluid is None:
            # TODO: Unit test
            fluid = ''
        # join them into a branch
        # -----------------------
        # np1_inlet -> np1 -> np1_np2_node -> np2 -> np2_outlet
            # change the node names in the component
            # empty the old branch
            # fill in the new components with the node names into this branch
        listofcomponents = _clean_listofcomponents(listofcomponents)
        connectcomponents(self.idf, listofcomponents, fluid=fluid)
    
        thebranch = branch
        componentsintobranch(self.idf, thebranch, listofcomponents, fluid=fluid)
    
        # # gather all renamed nodes
        # # do the renaming
        renamenodes(self.idf, 'node')
    
        # for use in bunch
        flnames = [field.replace(' ', '_') for field in self.loopfields]
    
        for i in range(1, 100000): # large range to hit end
            try:
                fieldname = 'Connector_%s_Object_Type' % (i, )
                ctype = self.s_connlist[fieldname]
            except bunch_subclass.BadEPFieldError:
                break
            if ctype.strip() == '':
                break  # this is never hit in unit tests
            fieldname = 'Connector_%s_Name' % (i, )
            cname = self.s_connlist[fieldname]
            connector = self.idf.getobject(ctype.upper(), cname)
            if connector.key == 'CONNECTOR:SPLITTER':
                firstbranchname = connector.Inlet_Branch_Name
                cbranchname = firstbranchname
                isfirst = True
            if connector.key == 'CONNECTOR:MIXER':
                lastbranchname = connector.Outlet_Branch_Name
                cbranchname = lastbranchname
                isfirst = False
            if cbranchname == thebranch.Name:
                # rename end nodes
                comps = getbranchcomponents(self.idf, thebranch)
                if isfirst:
                    comp = comps[0]
                    inletnodename = getnodefieldname(
                        comp,
                        "Inlet_Node_Name", fluid)
                    comp[inletnodename] = [
                        comp[inletnodename],
                        self.loop[flnames[0]]] # Plant_Side_Inlet_Node_Name
                else:
                    # TODO: unit test
                    comp = comps[-1]
                    outletnodename = getnodefieldname(
                        comp,
                        "Outlet_Node_Name", fluid)
                    comp[outletnodename] = [
                        comp[outletnodename],
                        self.loop[flnames[1]]] # .Plant_Side_Outlet_Node_Name
    
        if fluid.upper() == 'WATER':
            for i in range(1, 100000): # large range to hit end
                try:
                    fieldname = 'Connector_%s_Object_Type' % (i, )
                    ctype = self.d_connlist[fieldname]
                except bunch_subclass.BadEPFieldError:
                    break
                if ctype.strip() == '':
                    # TODO: Unit test
                    break
                fieldname = 'Connector_%s_Name' % (i, )
                cname = self.d_connlist[fieldname]
                connector = self.idf.getobject(ctype.upper(), cname)
                if connector.key == 'CONNECTOR:SPLITTER':
                    firstbranchname = connector.Inlet_Branch_Name
                    cbranchname = firstbranchname
                    isfirst = True
                if connector.key == 'CONNECTOR:MIXER':
                    lastbranchname = connector.Outlet_Branch_Name
                    cbranchname = lastbranchname
                    isfirst = False
                if cbranchname == thebranch.Name:
                    # TODO: unit test
                    # rename end nodes
                    comps = getbranchcomponents(self.idf, thebranch)
                    if isfirst:
                        comp = comps[0]
                        inletnodename = getnodefieldname(
                            comp,
                            "Inlet_Node_Name", fluid)
                        comp[inletnodename] = [
                            comp[inletnodename],
                            self.loop[flnames[4]]] #.Demand_Side_Inlet_Node_Name
                    if not isfirst:
                        comp = comps[-1]
                        outletnodename = getnodefieldname(
                            comp,
                            "Outlet_Node_Name", fluid)
                        comp[outletnodename] = [
                            comp[outletnodename],
                            self.loop[flnames[5]]] # .Demand_Side_Outlet_Node_Name
    
        # # gather all renamed nodes
        # # do the renaming
        renamenodes(self.idf, 'node')
    
        return thebranch

class AirLoopHVAC(Loop):
    
    loopfields = [
        'Branch List Name',
        'Connector List Name',
        'Supply Side Inlet Node Name',
        'Demand Side Outlet Node Name',
        'Demand Side Inlet Node Names',
        'Supply Side Outlet Node Names']
    
    def set_branchlists(self):
        self.supply_branchlist = self.idf.newidfobject(
            "BRANCHLIST", 
            self.newloop.Branch_List_Name)
        
    def make_demand_branches(self):
        make_air_demand_loop(self.idf, self.dloop)
        self.d_branches = []
    
    def rename_endpoints(self):
        return
    
    def make_supply_connectorlists(self):
        self.s_connlist = self.idf.newidfobject(
            "CONNECTORLIST", self.newloop.Connector_List_Name)
        self.s_connlist.Connector_1_Object_Type = "Connector:Splitter"
        self.s_connlist.Connector_1_Name = "%s_supply_splitter" % self.newloop.Name
        self.s_connlist.Connector_2_Object_Type = "Connector:Mixer"
        self.s_connlist.Connector_2_Name = "%s_supply_mixer" % self.newloop.Name

    def make_demand_connectorlists(self):
        return
    
    def make_splitters_and_mixers(self):
        make_air_splitters_mixers_and_paths(
            self.idf, self.newloop.Name, self.dloop, self.newloop)
    
    
class PlantLoop(Loop):
    
    loopfields = [
        'Plant Side Inlet Node Name',
        'Plant Side Outlet Node Name',
        'Plant Side Branch List Name',
        'Plant Side Connector List Name',
        'Demand Side Inlet Node Name',
        'Demand Side Outlet Node Name',
        'Demand Side Branch List Name',
        'Demand Side Connector List Name']
    
    def set_branchlists(self):
        self.supply_branchlist = self.idf.newidfobject(
            "BRANCHLIST", 
            self.newloop.Plant_Side_Branch_List_Name)
        self.demand_branchlist = self.idf.newidfobject(
            "BRANCHLIST", 
            self.newloop.Demand_Side_Branch_List_Name)

    def make_supply_connectorlists(self):
        s_connlist = self.idf.newidfobject(
            "CONNECTORLIST", self.newloop.Plant_Side_Connector_List_Name)
        s_connlist.Connector_1_Object_Type = "Connector:Splitter"
        s_connlist.Connector_1_Name = "%s_supply_splitter" % self.newloop.Name
        s_connlist.Connector_2_Object_Type = "Connector:Mixer"
        s_connlist.Connector_2_Name = "%s_supply_mixer" % self.newloop.Name
        self.s_connlist = s_connlist
    
    def make_demand_connectorlists(self):
        d_connlist = self.idf.newidfobject(
            "CONNECTORLIST", 
            self.newloop.Demand_Side_Connector_List_Name)
        d_connlist.Connector_1_Object_Type = "Connector:Splitter"
        d_connlist.Connector_1_Name = "%s_demand_splitter" % self.newloop.Name
        d_connlist.Connector_2_Object_Type = "Connector:Mixer"
        d_connlist.Connector_2_Name = "%s_demand_mixer" % self.newloop.Name
        self.d_connlist = d_connlist


class CondenserLoop(Loop):
    
    loopfields = [
        'Condenser Side Inlet Node Name',
        'Condenser Side Outlet Node Name',
        'Condenser Side Branch List Name',
        'Condenser Side Connector List Name',
        'Demand Side Inlet Node Name',
        'Demand Side Outlet Node Name',
        'Condenser Demand Side Branch List Name',
        'Condenser Demand Side Connector List Name']

    def set_branchlists(self):
        self.supply_branchlist = self.idf.newidfobject(
            "BRANCHLIST", 
            self.newloop.Condenser_Side_Branch_List_Name)
        self.demand_branchlist = self.idf.newidfobject(
            "BRANCHLIST", 
            self.newloop.Condenser_Demand_Side_Branch_List_Name)

    def make_supply_connectorlists(self):
        s_connlist = self.idf.newidfobject(
            "CONNECTORLIST", self.newloop.Condenser_Side_Connector_List_Name)
        s_connlist.Connector_1_Object_Type = "Connector:Splitter"
        s_connlist.Connector_1_Name = "%s_supply_splitter" % self.newloop.Name
        s_connlist.Connector_2_Object_Type = "Connector:Mixer"
        s_connlist.Connector_2_Name = "%s_supply_mixer" % self.newloop.Name
        self.s_connlist = s_connlist

    def make_demand_connectorlists(self):
        d_connlist = self.idf.newidfobject(
            "CONNECTORLIST", 
            self.newloop.Condenser_Demand_Side_Connector_List_Name)
        d_connlist.Connector_1_Object_Type = "Connector:Splitter"
        d_connlist.Connector_1_Name = "%s_demand_splitter" % self.newloop.Name
        d_connlist.Connector_2_Object_Type = "Connector:Mixer"
        d_connlist.Connector_2_Name = "%s_demand_mixer" % self.newloop.Name
        self.d_connlist = d_connlist


def initialise_loop(newloop, fields):
    """Initialise fields in a loop.
    
    These vary by type of loop.
    
    """
    # for use in bunch
    flnames = [sanitizefieldname(f) for f in fields]
    # simplify naming
    fields = simplify_names(fields)
    # make fieldnames in the loop
    fieldnames = ['%s %s' % (newloop.Name, field) for field in fields]
    for fieldname, thefield in zip(fieldnames, flnames):
        newloop[thefield] = fieldname


def pipebranch(idf, branchname):
    """make a branch with a pipe
    use standard inlet outlet names"""
    # make the pipe component first
    pname = "%s_pipe" % (branchname, )
    pipe = pipecomponent(idf, pname)
    # now make the branch with the pipe in it
    branch = idf.newidfobject("BRANCH", branchname)
    branch.Component_1_Object_Type = 'Pipe:Adiabatic'
    branch.Component_1_Name = pname
    branch.Component_1_Inlet_Node_Name = pipe.Inlet_Node_Name
    branch.Component_1_Outlet_Node_Name = pipe.Outlet_Node_Name
    branch.Component_1_Branch_Control_Type = "Bypass"
    return branch


def pipecomponent(idf, pname):
    """make a pipe component
    generate inlet outlet names"""
    pipe = idf.newidfobject("Pipe:Adiabatic".upper(), pname)
    pipe.Inlet_Node_Name = "%s_inlet" % (pname, )
    pipe.Outlet_Node_Name = "%s_outlet" % (pname, )
    return pipe


def ductbranch(idf, bname):
    """make a branch with a duct
    use standard inlet outlet names"""
    # make the duct component first
    pname = "%s_duct" % (bname, )
    duct = ductcomponent(idf, pname)
    # now make the branch with the duct in it
    branch = idf.newidfobject("BRANCH", bname)
    branch.Component_1_Object_Type = 'duct'
    branch.Component_1_Name = pname
    branch.Component_1_Inlet_Node_Name = duct.Inlet_Node_Name
    branch.Component_1_Outlet_Node_Name = duct.Outlet_Node_Name
    branch.Component_1_Branch_Control_Type = "Bypass"
    return branch


def ductcomponent(idf, dname):
    """make a duct component
    generate inlet outlet names"""
    duct = idf.newidfobject("duct".upper(), dname)
    duct.Inlet_Node_Name = "%s_inlet" % (dname, )
    duct.Outlet_Node_Name = "%s_outlet" % (dname, )
    return duct


def getbranchcomponents(idf, branch, utest=False):
    """get the components of the branch"""
    fobjtype = 'Component_%s_Object_Type'
    fobjname = 'Component_%s_Name'
    complist = []
    for i in range(1, 100000):
        try:
            objtype = branch[fobjtype % (i, )]
            if objtype.strip() == '':
                break
            objname = branch[fobjname % (i, )]
            complist.append((objtype, objname))
        except bunch_subclass.BadEPFieldError:
            # TODO: unit test
            # When should this be triggered?
            break
    if utest:
        return complist
    else:
        return [idf.getobject(ot, on) for ot, on in complist]


def renamenodes(idf, fieldtype):
    """rename all the changed nodes"""
    renameds = []
    for key in idf.model.dtls:
        for idfobject in idf.idfobjects[key]:
            for fieldvalue in idfobject.obj:
                if type(fieldvalue) is list:
                    if fieldvalue not in renameds:
                        cpvalue = copy.copy(fieldvalue)
                        renameds.append(cpvalue)

    # do the renaming
    for key in idf.model.dtls:
        for idfobject in idf.idfobjects[key]:
            for i, fieldvalue in enumerate(idfobject.obj):
                itsidd = idfobject.objidd[i]
                if 'type' in itsidd:
                    if itsidd['type'][0] == fieldtype:
                        tempdct = dict(renameds)
                        if type(fieldvalue) is list:
                            fieldvalue = fieldvalue[-1]
                            idfobject.obj[i] = fieldvalue
                        else:
                            if fieldvalue in tempdct:
                                fieldvalue = tempdct[fieldvalue]
                                idfobject.obj[i] = fieldvalue


def getfieldnamesendswith(idfobject, endswith):
    """get the filednames for the idfobject based on endswith"""
    objls = idfobject.objls
    tmp = [name for name in objls if name.endswith(endswith)]
    if tmp == []:
        # TODO: unit test
        pass
    return [name for name in objls if name.endswith(endswith)]


def getnodefieldname(idfobject, endswith, fluid=None, startswith=None):
    """return the field name of the node
    fluid is only needed if there are air and water nodes
    fluid is Air or Water or ''.
    if the fluid is Steam, use Water"""
    if startswith is None:
        startswith = ''
    if fluid is None:
        # TODO: unit test
        fluid = ''
    nodenames = getfieldnamesendswith(idfobject, endswith)
    nodenames = [name for name in nodenames if name.startswith(startswith)]
    fnodenames = [nd for nd in nodenames if nd.find(fluid) != -1]
    fnodenames = [name for name in fnodenames if name.startswith(startswith)]
    if len(fnodenames) == 0:
        nodename = nodenames[0]
    else:
        nodename = fnodenames[0]
    return nodename


def connectcomponents(idf, components, fluid=None):
    """rename nodes so that the components get connected
    fluid is only needed if there are air and water nodes
    fluid is Air or Water or ''.
    if the fluid is Steam, use Water"""
    if fluid is None:
        # TODO: unit test
        fluid = ''
    if len(components) == 1:
        # TODO: unit test
        thiscomp, thiscompnode = components[0]
        initinletoutlet(idf, thiscomp, thiscompnode, force=False)
        outletnodename = getnodefieldname(thiscomp, "Outlet_Node_Name",
                                          fluid=fluid, startswith=thiscompnode)
        thiscomp[outletnodename] = [thiscomp[outletnodename],
                                    thiscomp[outletnodename]]
        # inletnodename = getnodefieldname(nextcomp, "Inlet_Node_Name", fluid)
        # nextcomp[inletnodename] = [nextcomp[inletnodename], betweennodename]
        return components
    for i in range(len(components) - 1):
        thiscomp, thiscompnode = components[i]
        nextcomp, nextcompnode = components[i + 1]
        initinletoutlet(idf, thiscomp, thiscompnode, force=False)
        initinletoutlet(idf, nextcomp, nextcompnode, force=False)
        betweennodename = "%s_%s_node" % (thiscomp.Name, nextcomp.Name)
        outletnodename = getnodefieldname(thiscomp, "Outlet_Node_Name",
                                          fluid=fluid, startswith=thiscompnode)
        thiscomp[outletnodename] = [thiscomp[outletnodename], betweennodename]
        inletnodename = getnodefieldname(nextcomp, "Inlet_Node_Name", fluid)
        nextcomp[inletnodename] = [nextcomp[inletnodename], betweennodename]
    return components


def initinletoutlet(idf, idfobject, thisnode, force=False):
    """initialze values for all the inlet outlet nodes for the object.
    if force == False, it willl init only if field = '' """
    def blankfield(fieldvalue):
        """test for blank field"""
        try:
            if fieldvalue.strip() == '':
                return True
            else:
                return False
        except AttributeError: # field may be a list
            return False
        
    def trimfields(fields, thisnode):
        if len(fields) > 1:
            if thisnode is not None:
                fields = [field for field in fields
                          if field.startswith(thisnode)]
                return fields
            else:
                # TODO: unit test
                print("Where should this loop connect ?")
                print("%s - %s" % (idfobject.key, idfobject.Name))
                print([field.split("Inlet_Node_Name")[0]
                       for field in inletfields])
                raise WhichLoopError
        else:
            return fields

    inletfields = getfieldnamesendswith(idfobject, "Inlet_Node_Name")
    inletfields = trimfields(inletfields, thisnode) # or warn with exception
    for inletfield in inletfields:
        if blankfield(idfobject[inletfield]) == True or force == True:
            idfobject[inletfield] = "%s_%s" % (idfobject.Name, inletfield)
    outletfields = getfieldnamesendswith(idfobject, "Outlet_Node_Name")
    outletfields = trimfields(outletfields, thisnode) # or warn with exception
    for outletfield in outletfields:
        if blankfield(idfobject[outletfield]) == True or force == True:
            idfobject[outletfield] = "%s_%s" % (idfobject.Name, outletfield)
    return idfobject


def componentsintobranch(idf, branch, listofcomponents, fluid=None):
    """insert a list of components into a branch
    fluid is only needed if there are air and water nodes in same object
    fluid is Air or Water or ''.
    if the fluid is Steam, use Water"""
    if fluid is None:
        # TODO: unit test
        fluid = ''
    componentlist = [item[0] for item in listofcomponents]
    # assumes that the nodes of the component connect to each other
    # empty branch if it has existing components
    thebranchname = branch.Name
    thebranch = idf.removeextensibles('BRANCH', thebranchname) # empty the branch
    # fill in the new components with the node names into this branch
        # find the first extensible field and fill in the data in obj.
    e_index = idf.getextensibleindex('BRANCH', thebranchname)
    theobj = thebranch.obj
    modeleditor.extendlist(theobj, e_index) # just being careful here
    for comp, compnode in listofcomponents:
        theobj.append(comp.key)
        theobj.append(comp.Name)
        inletnodename = getnodefieldname(comp, "Inlet_Node_Name", fluid=fluid,
                                         startswith=compnode)
        theobj.append(comp[inletnodename])
        outletnodename = getnodefieldname(comp, "Outlet_Node_Name",
                                          fluid=fluid, startswith=compnode)
        theobj.append(comp[outletnodename])
        theobj.append('')

    return thebranch


def doingtesting(testing, testn, result=None):
    """doing testing"""
    # TODO: We can do better than this
    testn += 1
    if testing == testn:
        print(testing)
        return
    else:
        return testn


def simplify_names(fields):
    """Change names of loop elements
    
    Parameters
    ----------
    fields : list
        List of field names.
    
    Returns
    -------
    list

    """
    fields = [f.replace('Condenser Side', 'Cond_Supply') for f in fields]
    fields = [f.replace('Plant Side', 'Supply') for f in fields]
    fields = [f.replace('Demand Side', 'Demand') for f in fields]
    fields = [f[:f.find('Name') - 1] for f in fields]
    fields = [f.replace(' Node', '') for f in fields]
    fields = [f.replace(' List', 's') for f in fields]
    
    return fields


def make_air_demand_loop(idf, dloop):
    """Make the demand side of an air loop
    """
    _inlet, zones, _outlet = dloop
    #ZoneHVAC:EquipmentConnections
    for zone in zones:
        equipconn = idf.newidfobject("ZoneHVAC:EquipmentConnections".upper())
        equipconn.Zone_Name = zone
        fldname = "Zone_Conditioning_Equipment_List_Name"
        equipconn[fldname] = "%s equip list" % (zone, )
        fldname = "Zone_Air_Inlet_Node_or_NodeList_Name"
        equipconn[fldname] = "%s Inlet Node" % (zone, )
        fldname = "Zone_Air_Node_Name"
        equipconn[fldname] = "%s Node" % (zone, )
        fldname = "Zone_Return_Air_Node_Name"
        equipconn[fldname] = "%s Outlet Node" % (zone, )
    
    # make ZoneHVAC:EquipmentList
    for zone in zones:
        z_equiplst = idf.newidfobject("ZoneHVAC:EquipmentList".upper())
        z_equipconn = modeleditor.getobjects(idf.idfobjects, idf.model, idf.idd_info, "ZoneHVAC:EquipmentConnections".upper(), #places=7,
            **dict(Zone_Name=zone))[0]
        z_equiplst.Name = z_equipconn.Zone_Conditioning_Equipment_List_Name
        fld = "Zone_Equipment_1_Object_Type"
        z_equiplst[fld] = "AirTerminal:SingleDuct:Uncontrolled"
        z_equiplst.Zone_Equipment_1_Name = "%sDirectAir" % (zone, )
        z_equiplst.Zone_Equipment_1_Cooling_Sequence = 1
        z_equiplst.Zone_Equipment_1_Heating_or_NoLoad_Sequence = 1
    
    # make AirTerminal:SingleDuct:Uncontrolled
    for zone in zones:
        z_equipconn = modeleditor.getobjects(
            idf.idfobjects, idf.model, idf.idd_info, 
            "ZoneHVAC:EquipmentConnections".upper(), #places=7,
            **dict(Zone_Name=zone))[0]
        key = "AirTerminal:SingleDuct:Uncontrolled".upper()
        z_airterm = idf.newidfobject(key)
        z_airterm.Name = "%sDirectAir" % (zone, )
        fld1 = "Zone_Supply_Air_Node_Name"
        fld2 = "Zone_Air_Inlet_Node_or_NodeList_Name"
        z_airterm[fld1] = z_equipconn[fld2]
        z_airterm.Maximum_Air_Flow_Rate = 'autosize'
    
    
def make_air_splitters_mixers_and_paths(idf, loopname, dloop, newloop):
    """Make splitters and mixers and supply and return paths for an air loop.
    """
    _inlet, zones, _outlet = dloop
    # make AirLoopHVAC:ZoneSplitter
    z_splitter = idf.newidfobject("AIRLOOPHVAC:ZONESPLITTER")
    z_splitter.Name = "%s Demand Side Splitter" % (loopname, )
    z_splitter.Inlet_Node_Name = newloop.Demand_Side_Inlet_Node_Names
    for i, zone in enumerate(zones):
        z_equipconn = modeleditor.getobjects(
            idf.idfobjects, idf.model, idf.idd_info, 
            "ZoneHVAC:EquipmentConnections".upper(),
            **dict(Zone_Name=zone))[0]
        fld = "Outlet_%s_Node_Name" % (i + 1, )
        z_splitter[fld] = z_equipconn.Zone_Air_Inlet_Node_or_NodeList_Name
    
    # make AirLoopHVAC:ZoneMixer
    z_mixer = idf.newidfobject("AIRLOOPHVAC:ZONEMIXER")
    z_mixer.Name = "%s Demand Side Mixer" % (loopname, )
    z_mixer.Outlet_Node_Name = newloop.Demand_Side_Outlet_Node_Name
    for i, zone in enumerate(zones):
        z_equipconn = modeleditor.getobjects(
            idf.idfobjects, idf.model, idf.idd_info, 
            "ZoneHVAC:EquipmentConnections".upper(), #places=7,
            **dict(Zone_Name=zone))[0]
        fld = "Inlet_%s_Node_Name" % (i + 1, )
        z_mixer[fld] = z_equipconn.Zone_Return_Air_Node_Name
    
    # make AirLoopHVAC:SupplyPath
    z_supplypth = idf.newidfobject("AIRLOOPHVAC:SUPPLYPATH")
    z_supplypth.Name = "%sSupplyPath" % (loopname, )
    fld1 = "Supply_Air_Path_Inlet_Node_Name"
    fld2 = "Demand_Side_Inlet_Node_Names"
    z_supplypth[fld1] = newloop[fld2]
    z_supplypth.Component_1_Object_Type = "AirLoopHVAC:ZoneSplitter"
    z_supplypth.Component_1_Name = z_splitter.Name
    
    # make AirLoopHVAC:ReturnPath
    z_returnpth = idf.newidfobject("AIRLOOPHVAC:RETURNPATH")
    z_returnpth.Name = "%sReturnPath" % (loopname, )
    fld1 = "Return_Air_Path_Outlet_Node_Name"
    fld2 = "Demand_Side_Outlet_Node_Name"
    z_returnpth[fld1] = newloop[fld2]
    z_returnpth.Component_1_Object_Type = "AirLoopHVAC:ZoneMixer"
    z_returnpth.Component_1_Name = z_mixer.Name
    
    
def rename_endpoints(idf, newloop, demand_branchnames, supply_branches):
    """Rename inlet outlet of endpoints of loop
    """
    anode = "Component_1_Inlet_Node_Name"
    if newloop.key == 'CONDENSERLOOP':
        sameinnode = "Condenser_Side_Inlet_Node_Name"
        sameoutnode = "Condenser_Side_Outlet_Node_Name" # TODO : change ?
    elif newloop.key == 'PLANTLOOP':
        sameinnode = "Plant_Side_Inlet_Node_Name"
        sameoutnode = "Plant_Side_Outlet_Node_Name"
    supply_branches[0][anode] = newloop[sameinnode]
    anode = "Component_1_Outlet_Node_Name"
    supply_branches[-1][anode] = newloop[sameoutnode]
    # rename inlet outlet of endpoints of loop - rename in pipe
    pipe_name = supply_branches[0]['Component_1_Name'] # get the pipe name
    apipe = idf.getobject('Pipe:Adiabatic'.upper(), pipe_name) # get pipe
    apipe.Inlet_Node_Name = newloop[sameinnode]
    pipe_name = supply_branches[-1]['Component_1_Name'] # get the pipe name
    apipe = idf.getobject('Pipe:Adiabatic'.upper(), pipe_name) # get pipe
    apipe.Outlet_Node_Name = newloop[sameoutnode]
    # demand side
    demand_branches = [pipebranch(idf, branch) for branch in demand_branchnames]
    
    # rename inlet outlet of endpoints of loop - rename in branch
    anode = "Component_1_Inlet_Node_Name"
    sameinnode = "Demand_Side_Inlet_Node_Name"
    demand_branches[0][anode] = newloop[sameinnode]
    anode = "Component_1_Outlet_Node_Name"
    sameoutnode = "Demand_Side_Outlet_Node_Name"
    demand_branches[-1][anode] = newloop[sameoutnode]
    # rename inlet outlet of endpoints of loop - rename in pipe
    pipe_name = demand_branches[0]['Component_1_Name'] # get the pipe name
    apipe = idf.getobject('Pipe:Adiabatic'.upper(), pipe_name) # get pipe
    apipe.Inlet_Node_Name = newloop[sameinnode]
    pipe_name = demand_branches[-1]['Component_1_Name'] # get the pipe name
    apipe = idf.getobject('Pipe:Adiabatic'.upper(), pipe_name) # get pipe
    apipe.Outlet_Node_Name = newloop[sameoutnode]


def make_connectorlists(idf, loopname, newloop):
    """Make the connectorlist and fill fields.
    
    Parameters
    ----------
    idf : IDF object
        The IDF.
    loopname : str
        Name of the loop.
    newloop : EPBunch
        The loop under construction.
    
    Returns
    -------
    EPBunch, EPBunch
        Supply and demand CONNECTORLIST objects.
        
    """
    if newloop.key == 'CONDENSERLOOP':
        s_connlist = idf.newidfobject(
            "CONNECTORLIST", newloop.Condenser_Side_Connector_List_Name)
    elif newloop.key == 'PLANTLOOP':
        s_connlist = idf.newidfobject(
            "CONNECTORLIST", newloop.Plant_Side_Connector_List_Name)
    elif newloop.key == 'AIRLOOPHVAC':
        # TODO: unit test
        s_connlist = idf.newidfobject(
            "CONNECTORLIST", newloop.Connector_List_Name)
    s_connlist.Connector_1_Object_Type = "Connector:Splitter"
    s_connlist.Connector_1_Name = "%s_supply_splitter" % (loopname, )
    s_connlist.Connector_2_Object_Type = "Connector:Mixer"
    s_connlist.Connector_2_Name = "%s_supply_mixer" % (loopname, )
    if newloop.key == 'CONDENSERLOOP':
        d_connlist = idf.newidfobject(
            "CONNECTORLIST", 
            newloop.Condenser_Demand_Side_Connector_List_Name)
    elif newloop.key == 'PLANTLOOP':
        d_connlist = idf.newidfobject(
            "CONNECTORLIST", 
            newloop.Demand_Side_Connector_List_Name)
    elif newloop.key == 'AIRLOOPHVAC':
        # TODO: unit test
        d_connlist = []

    if d_connlist:
        d_connlist.Connector_1_Object_Type = "Connector:Splitter"
        d_connlist.Connector_1_Name = "%s_demand_splitter" % (loopname, )
        d_connlist.Connector_2_Object_Type = "Connector:Mixer"
        d_connlist.Connector_2_Name = "%s_demand_mixer" % (loopname, )
    
    return s_connlist, d_connlist


def make_splitters_and_mixers(idf, sloop, dloop, sconnlist, dconnlist):
    """Make splitters and mixers for plant or condenser loops
    
    Parameters
    ----------
    idf : IDF object
        The IDF.
    sloop : list
        List of elements on the supply loop.
    dloop : list
        List of elements on the demand loop.
    sconnlist : list
        List of splitters and mixers on the supply loop.
    dconnlist : list
        List of splitters and mixers on the demand loop.
    """
    supply_splitter = idf.newidfobject(
        "CONNECTOR:SPLITTER", 
        sconnlist.Connector_1_Name)
    supply_splitter.obj.extend([sloop[0]] + sloop[1])
    supply_mixer = idf.newidfobject(
        "CONNECTOR:MIXER", 
        sconnlist.Connector_2_Name)
    supply_mixer.obj.extend([sloop[-1]] + sloop[1])

    if dconnlist:
        demand_splitter = idf.newidfobject(
            "CONNECTOR:SPLITTER", 
            dconnlist.Connector_1_Name)
        demand_splitter.obj.extend([dloop[0]] + dloop[1])
        demand_mixer = idf.newidfobject(
            "CONNECTOR:MIXER", 
            dconnlist.Connector_2_Name)
        demand_mixer.obj.extend([dloop[-1]] + dloop[1])


def _clean_listofcomponents(listofcomponents):
    """force it to be a list of tuples"""
    def totuple(item):
        """return a tuple"""
        if isinstance(item, (tuple, list)):
            return item
        else:
            return (item, None)
    return [totuple(item) for item in listofcomponents]


def _clean_listofcomponents_tuples(listofcomponents_tuples):
    """force 3 items in the tuple"""
    def pad(item, n):
        """return a n-item tuple"""
        return item + (None, ) * (n - len(item))
    return [pad(item, 3) for item in listofcomponents_tuples]


def getmakeidfobject(idf, key, name):
    """get idfobject or make it if it does not exist"""
    # TODO: unit test
    # I often write something like this and didn't know it was already here.
    # Perhaps move to modeleditor.IDF()?
    idfobject = idf.getobject(key, name)
    if not idfobject:
        return idf.newidfobject(key, name)
    else:
        return idfobject


def replacebranch1(idf, loop, branchname, listofcomponents_tuples, fluid=None,
                   debugsave=False):
    """do I even use this ? .... yup! I do"""
    # TODO: Unit test
    if fluid is None:
        fluid = ''
    listofcomponents_tuples = _clean_listofcomponents_tuples(listofcomponents_tuples)
    branch = idf.getobject('BRANCH', branchname) # args are (key, name)
    listofcomponents = []
    for comp_type, comp_name, compnode in listofcomponents_tuples:
        comp = getmakeidfobject(idf, comp_type.upper(), comp_name)
        listofcomponents.append((comp, compnode))
    newbr = replacebranch(idf, loop, branch, listofcomponents,
                          debugsave=debugsave, fluid=fluid)
    return newbr


def replacebranch(idf, loop, branch,
                  listofcomponents, fluid=None,
                  debugsave=False,
                  testing=None):
    """It will replace the components in the branch with components in
    listofcomponents"""
    if fluid is None:
        # TODO: Unit test
        fluid = ''
    # join them into a branch
    # -----------------------
    # np1_inlet -> np1 -> np1_np2_node -> np2 -> np2_outlet
        # change the node names in the component
        # empty the old branch
        # fill in the new components with the node names into this branch
    listofcomponents = _clean_listofcomponents(listofcomponents)

    components = [item[0] for item in listofcomponents]
    connectcomponents(idf, listofcomponents, fluid=fluid)

    thebranch = branch
    componentsintobranch(idf, thebranch, listofcomponents, fluid=fluid)

    # # gather all renamed nodes
    # # do the renaming
    renamenodes(idf, 'node')

    # check for the end nodes of the loop
    fields = loop.loopfields
    # for use in bunch
    flnames = [field.replace(' ', '_') for field in fields]

    if fluid.upper() == 'WATER':
        supplyconlistname = loop.loop[flnames[3]]
        # Plant_Side_Connector_List_Name or Condenser_Side_Connector_List_Name
    elif fluid.upper() == 'AIR':
        # TODO: unit test
        supplyconlistname = loop.loop[flnames[1]] # Connector_List_Name'
    supplyconlist = idf.getobject('CONNECTORLIST', supplyconlistname)
    for i in range(1, 100000): # large range to hit end
        try:
            fieldname = 'Connector_%s_Object_Type' % (i, )
            ctype = supplyconlist[fieldname]
        except bunch_subclass.BadEPFieldError:
            break
        if ctype.strip() == '':
            break  # this is never hit in unit tests
        fieldname = 'Connector_%s_Name' % (i, )
        cname = supplyconlist[fieldname]
        connector = idf.getobject(ctype.upper(), cname)
        if connector.key == 'CONNECTOR:SPLITTER':
            firstbranchname = connector.Inlet_Branch_Name
            cbranchname = firstbranchname
            isfirst = True
        if connector.key == 'CONNECTOR:MIXER':
            lastbranchname = connector.Outlet_Branch_Name
            cbranchname = lastbranchname
            isfirst = False
        if cbranchname == thebranch.Name:
            # rename end nodes
            comps = getbranchcomponents(idf, thebranch)
            if isfirst:
                comp = comps[0]
                inletnodename = getnodefieldname(
                    comp,
                    "Inlet_Node_Name", fluid)
                comp[inletnodename] = [
                    comp[inletnodename],
                    loop.loop[flnames[0]]] # Plant_Side_Inlet_Node_Name
            else:
                # TODO: unit test
                comp = comps[-1]
                outletnodename = getnodefieldname(
                    comp,
                    "Outlet_Node_Name", fluid)
                comp[outletnodename] = [
                    comp[outletnodename],
                    loop.loop[flnames[1]]] # .Plant_Side_Outlet_Node_Name

    if fluid.upper() == 'WATER':
        demandconlistname = loop.loop[flnames[7]] # .Demand_Side_Connector_List_Name
        demandconlist = idf.getobject('CONNECTORLIST', demandconlistname)
        for i in range(1, 100000): # large range to hit end
            try:
                fieldname = 'Connector_%s_Object_Type' % (i, )
                ctype = demandconlist[fieldname]
            except bunch_subclass.BadEPFieldError:
                break
            if ctype.strip() == '':
                # TODO: Unit test
                break
            fieldname = 'Connector_%s_Name' % (i, )
            cname = demandconlist[fieldname]
            connector = idf.getobject(ctype.upper(), cname)
            if connector.key == 'CONNECTOR:SPLITTER':
                firstbranchname = connector.Inlet_Branch_Name
                cbranchname = firstbranchname
                isfirst = True
            if connector.key == 'CONNECTOR:MIXER':
                lastbranchname = connector.Outlet_Branch_Name
                cbranchname = lastbranchname
                isfirst = False
            if cbranchname == thebranch.Name:
                # TODO: unit test
                # rename end nodes
                comps = getbranchcomponents(idf, thebranch)
                if isfirst:
                    comp = comps[0]
                    inletnodename = getnodefieldname(
                        comp,
                        "Inlet_Node_Name", fluid)
                    comp[inletnodename] = [
                        comp[inletnodename],
                        loop.loop[flnames[4]]] #.Demand_Side_Inlet_Node_Name
                if not isfirst:
                    comp = comps[-1]
                    outletnodename = getnodefieldname(
                        comp,
                        "Outlet_Node_Name", fluid)
                    comp[outletnodename] = [
                        comp[outletnodename],
                        loop.loop[flnames[5]]] # .Demand_Side_Outlet_Node_Name

    # # gather all renamed nodes
    # # do the renaming
    renamenodes(idf, 'node')

    return thebranch


def flattencopy(lst):
    """flatten and return a copy of the list
    inefficient on large lists"""
    # modified from
    # http://stackoverflow.com/questions/2158395/flatten-an-irregular-list-of-lists-in-python
    thelist = copy.deepcopy(lst)
    list_is_nested = True
    while list_is_nested:                 #outer loop
        keepchecking = False
        atemp = []
        for element in thelist:         #inner loop
            if isinstance(element, list):
                atemp.extend(element)
                keepchecking = True
            else:
                atemp.append(element)
        list_is_nested = keepchecking     #determine if outer loop exits
        thelist = atemp[:]
    return thelist
