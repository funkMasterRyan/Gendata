import numpy as np
import matplotlib.pyplot as plt
import struct
from Gendata import gendata as gen
from BLS.Data.Cat.scripts import load_cat
import xarray as xr
import BLS.Calc.coordinate_transforms as trans


##====================================================##
##            >>--regridMaster.py--<<
## 
## Ryan Patmore 17/07/15
## Outputs all required for regridding in MITgcm
##====================================================##

case_name = 'ISOBL_141'

# Set grid
cartesian    = 1
res_multiplier = 1.0 
res          = 10.0/res_multiplier
zRes         = 1
ydim         = int(200*res_multiplier)
xdim         = int(200*res_multiplier)
zdim         = 104
latMax       = -1
latMin       = -75
z0           = 20

# Set bathymetry
depMax       = 9
wall_west    = 0
wall_east    = xdim
wall_south   = 0
wall_north   = 0 
 
iceDep = 1

# EOS
rhoConst = 1030
tAlpha = 3.9e-5
sBeta = 7.41e-4

g = 9.81

# Temperature
t_low  = 1.0000001 
t_high = 1

# Salinity
s_low  = 34.0 
s_high = 34.5

# Pressure
# suposed realistic values
#p_low  = 1000e2
p_low  = 1000e2
p_high = 4000e2
etaGrad = 0.00001

# Velocity
v_low = 1
v_high = 2

cd = 0.0012
       
wind       = 0
temp       = 0
salt       = 0
pressure   = 0
shice      = 0
rbcs       = 0



ini_params = { 'xdim'  : xdim,
               'ydim'  : ydim,
               'zdim'  : zdim,
               'g'     : g,
               'sBeta' : sBeta,
               'tAlpha': tAlpha,
               'rhoConst': rhoConst,
               'depMax': depMax,
               'iceDep': iceDep,
               's_low' : s_low,
               's_high' : s_high,
               't_low' : t_low,
               't_high': t_high }

state = gen.State(ini_params)

def get_cat_profile(time, quantity):
    cat = load_cat()
    cat_prof = cat.isel(TIME=time)
    cat_quantity = cat_prof[quantity]
    return cat_quantity

def ini_cat(time):
    ''' make files for cat initialiation '''

    # load cat profiles
    T = get_cat_profile(time, 'THETA_spatial_mean')
    S = get_cat_profile(time, 'SALT_spatial_mean')
    U = get_cat_profile(time, 'UVEL_spatial_mean')
    V = get_cat_profile(time, 'VVEL_spatial_mean')


    # set masked values
    freeze_T = -0.12195 - 2
    freeze_S = 34.5

    cat = xr.merge([T,S,U,V])

    # interp to 1 m grid
    cat = cat.interp({'new_Z': np.linspace(-101.5, 1.5, 104)},
                 kwargs={'fill_value':np.nan})
    array_shape = (state.ydim, state.xdim)
    dummy = xr.DataArray(np.full(array_shape, freeze_T), 
                         dims=['Y', 'X'],
                         coords={'X':np.arange(200),
                                 'Y':np.arange(200)})
    cat_3d = cat.broadcast_like(dummy, exclude='new_Z')
    cat_3d['X_dash'], cat_3d['Y_dash'], cat_3d['Z_dash'] = trans.rotate_coords(                                                           cat_3d.X, 
                                                          cat_3d.Y, 
                                                          cat_3d.new_Z,
                                                          cat_3d.X.mean(),
                                                          cat_3d.Y.mean(),
                                                          cat_3d.new_Z.mean(),
                                                          np.arctan(-1/100))
    # shift coords to leave ice gap
    #cat_3d['Z_dash'] = cat_3d['Z_dash'] - 2

    cat_3d = cat_3d.assign_coords(X_dash=cat_3d['X_dash'], 
                                  Z_dash=cat_3d['Z_dash'])
    cat_3d = cat_3d.isel(Y=0)
    #plt.figure()
    #plt.pcolor(cat_3d.X_dash, cat_3d.Z_dash,cat_3d.THETA_spatial_mean)
    #plt.show()
    from scipy.interpolate import griddata
    def interpolate(cat_3d, da):
        X, Z = np.meshgrid(cat_3d.X, cat_3d.new_Z)
        grid = griddata((cat_3d.X_dash.values.ravel(), 
                         cat_3d.Z_dash.values.ravel()),
                         cat_3d[da].values.ravel(),
                         (X, Z), method='linear')
        return grid
    ini_theta = interpolate(cat_3d, 'THETA_spatial_mean')
    ini_theta = np.broadcast_to(ini_theta.T, (200,200,104))
    ini_theta = np.moveaxis(ini_theta, 0, 1).T
    

    name  = case_name + '_ini_theta.bin'
    state.writeBin(ini_theta, name)
    y = state.readBin(name,int(xdim),int(ydim),int(zdim))
    fig = plt.figure(3)
    p = plt.pcolormesh(cat_3d.X, cat_3d.new_Z, y[:,0,:])
    plt.axis('equal')
    plt.colorbar(p)
    plt.title('temp')
    plt.show()

ini_cat(30)
    

# MITgcm binary file is saved in (x,y) format

def make_ini_temp():
    name = case_name + '_ini_temp.bin'
    #t0 = state.add_heat_blob(state.gridx, state.gridz, 90, 170, 15)
    #t0 = state.ini_field_hill(state.xdim, state.gridx, 0.1)
    #t = state.ini_field_linear_grad(state.zdim, state.gridz, t_low, t_high)
    
    hFacC = state.readBin('ISOBL_024_hFacC.bin',int(xdim),int(ydim), int(zdim))
    t = np.full(state.gridx.shape, -0.1451) # uniform pforce
    print (t.shape)
    ice_end = np.argmax(np.where(hFacC < 1 , t, 0), axis=0)
    bathy_start = np.argmax(np.where(hFacC[::-1] < 1 , t, 0), axis=0)
    for i in range(t.shape[2]):
        for j in range(t.shape[1]):
            for k in range(ice_end[j,i], 122-bathy_start[j,i]):
                t[k,j,i] = -0.1451 + ( (2/109) * k )
            for k in range(122-bathy_start[j,i], 122):
                t[k,j,i] = 1.8549
    plt.figure()
    p = plt.pcolor(t[:,0,:])
    plt.colorbar(p)
    plt.show()
    print ('tshape', t[4,0,0])
    #t[:2,:,:] = t[0,0,0]
    print ('tshape', t[4,0,0])
    #t = t0 + t1
    print (state.shape)
    #t = np.full(state.shape, 1)
    
    #t[2,0,-3] = 2
    #t[50,0,-10] = 2
    #t[1,0,-3] = 2
    print ('state.shape', state.shape)
    print ('gridz.shape', state.gridx.shape)
    state.writeBin(t,name)
    y = state.readBin(name,int(xdim),int(ydim),int(zdim))
    fig = plt.figure(3)
    p = plt.pcolormesh(y[:,0,:])
    plt.axis('equal')
    plt.colorbar(p)
    plt.title('temp')


def make_ini_salt():
    name = case_name + '_ini_salt.bin'
    s0 = state.ini_field_hill(state.xdim, state.gridx, 0.05)
    s1 = state.ini_field_linear_grad(state.zdim, state.gridz, t_low, t_high)
    s = s0 + s1
    s = np.full(state.gridx.shape, 34.5714) # uniform pforce
    state.writeBin(s,name)
    y = state.readBin(name,int(xdim),int(ydim),int(zdim))
    fig = plt.figure(4)
    p = plt.pcolormesh(y[:,0,:])
    plt.axis('equal')
    plt.colorbar(p)
    plt.title('temp')

def make_pressure_force():
    name = case_name + '_pForceX.bin'
    #pload = state.ini_p_force(state.xdim, state.gridx, p_low, p_high)
    #pload = pload * state.gridz[:,:,::-1] / state.gridz.max()
    pload = np.full(state.gridx.shape, rhoConst * g * etaGrad) # uniform pforce
    #pload = np.full(state.gridx.shape, g * etaGrad) # uniform pforce
    #pload = np.full(state.shape, 0)
    
    #pload[2,0,-2] = 0.001
    state.writeBin(pload,name)
    y = state.readBin(name,int(xdim),int(ydim),int(zdim))
    fig = plt.figure(4)
    print ('pressure shape', y.shape)
    p = plt.pcolormesh(y[:,0,:])
    plt.axis('equal')
    plt.colorbar(p)
    plt.title('pressure')

def make_ini_shice_topo(): 
    ShiceTopo  = case_name + '_ini_shice_topo.bin'
    shice_topo = - np.full((state.ydim, state.xdim), iceDep)
    #mesh = np.mgrid[0:int(ydim),0:int(xdim)][1]
    #h0 = -50
    #h1 = -2.5
    #dhdx = (h1 - h0) / (xdim - 1)
    #shice_topo = -50 + (mesh * dhdx)
    #b[:,:2]  = -50 
    #b[:,-2:] = -7.5

    # ---------------------------------------- #
    # shelf-ice topo Stepping for when hFacMin==1
    #step = 4
    #intervals = np.arange(int(step/2),100,step)
    #shice_topo[:,:intervals[0]] = - 1 - len(intervals) 
    #for i, pos in enumerate(intervals[::-1]):
    #    print ('pos', pos)
    #    print ('pos', pos-step)
    #    shice_topo[:,pos-step:pos] = -2 - i
    #shice_topo[:,intervals[-1]:] = - 1  
    # ---------------------------------------- #

    # ---------------------------------------- #
    # shelf-ice topo Stepping for when hFacMin!=1
    ice_min = -16
    ice_max = -8
    depths = np.linspace(ice_min,ice_max,xdim-2)
    print ('DEPTHS DIFF', depths)
    print ('shite shape DIFF', shice_topo.shape)
    shice_topo = shice_topo.astype('float64')
    print ('TYPE', shice_topo.dtype)
    for i, depth in enumerate(depths):
        shice_topo[:,i+1] = depth 
        print (shice_topo)
        print (depth)
    shice_topo[:,0] = ice_min
    shice_topo[:,-1] = ice_max
    # ---------------------------------------- #

    #pos = int(xdim/2)
    #shice_topo[:,:pos] = -2 
    #shice_topo[:,pos:pos + 1] = -2 
    #shice_topo[:,:25] = -3 
    #shice_topo[:,25:75] = -2 
    print ('shice topo', shice_topo)
    state.writeBin(shice_topo, ShiceTopo)
    y = state.readBin(ShiceTopo,int(xdim),int(ydim))
    fig = plt.figure(5)
    p = plt.plot(y[0])
    plt.axis('equal')
    ##plt.colorbar(p)
    plt.title('ini_shice')

def make_ini_shice_rho():
    ShiceTopo  = case_name + '_ini_shice_p.bin'
    shice_topo =  np.full((state.ydim, state.xdim), 0)
    state.writeBin(shice_topo, ShiceTopo)
    y = state.readBin(ShiceTopo,int(xdim),int(ydim))
    fig = plt.figure(7)
    p = plt.plot(y[0])
    plt.axis('equal')
    plt.title('ini_shice_p')


if shice:
    # Check for initial state files
    if temp == 0:
        t = np.full(state.gridx.shape, -1.9)
    if salt == 0:
        s = np.full(state.gridx.shape, 34.4)

    # Set file names
    ShicePFile = case_name + '_ini_shice_p.bin'
    ShiceTopo  = case_name + '_ini_shice_topo.bin'
    
    # Make setup files
    #iceProfile = np.zeros((ydim,xdim))
    #iceProfile[0,:] = -1
    #iceProfile[0,:2] = -2
    mesh = np.mgrid[0:int(ydim),0:int(xdim)][1]
    h0 = -50
    h1 = -1
    dhdx = (h1 - h0) / xdim
    iceProfile = h0 + (mesh * dhdx)
    hFacC = state.readBin('../SHELF_hFacC.data', x=int(xdim), y=int(ydim),
                                                     z=int(zdim))
    #hFacC = np.ones((zdim,ydim,xdim))

    # Create MITgcm input files
    shice_topo, shice_p = state.ini_shice(iceProfile, t, s, hFacC)
    state.writeBin(shice_p, ShicePFile)
    state.writeBin(shice_topo, ShiceTopo)

    # Plot binary
    y = state.readBin(ShicePFile,int(xdim),int(ydim))
    fig = plt.figure(5)
    p = plt.pcolormesh(y)
    plt.axis('equal')
    plt.colorbar(p)
    plt.title('shice')


def make_ini_vels(state):
    uName = case_name + '_ini_uvel.bin'
    vName = case_name + '_ini_vvel.bin'
    wName = case_name + '_ini_wvel.bin'
    #vels = state.add_heat_blob(state.gridx, state.gridz, 90, 100, 15)
    #vels = state.ini_field_linear_grad(state.zdim, state.gridz, v_low, v_high)

    # -- random kick -- #
    kick = 1e-3
    uVels = kick * (np.random.rand(*state.shape) - 0.5)
    vVels = kick * (np.random.rand(*state.shape) - 0.5)
    wVels = kick * (np.random.rand(*state.shape) - 0.5)

    expon = 0
    if expon:
        mesh = (np.mgrid[0:int(zdim),0:int(ydim),0:int(xdim)][0] /
                int(zdim)) - 1 
        exp = np.exp(mesh)[::-1]
        print ('EXP', exp)
    else:
        exp = 1

    uKick = uVels * exp 
    vKick = vVels * exp 
    wKick = wVels * exp 
    # -- random kick -- #


    #vels = np.full(state.shape, 0.0000001)
    
    #vels[2,0,-3] = 1
    state.writeBin(uKick,uName)
    state.writeBin(vKick,vName)
    state.writeBin(wKick,wName)
    plot_2d(state, uNname, xdim, ydim, zdim, title='vels',fnum=1)

def make_bathy(xdim, ydim, ini_params):
    name = case_name + '_bathy.bin'
    bathy = gen.Bathymetry(ini_params)
    b = bathy.get_bathy()#[::-1]
    mesh = np.mgrid[0:int(ydim),0:int(xdim)][1] 
     
    if hFacMin == 1: 
        # Bathy Stepping for when hFacMin=1
        step = 4
        intervals = np.arange(int(step/2),100,step)
        b[:,intervals[0]:] = -99  
        for i, pos in enumerate(intervals):
            print ('pos', pos)
            print ('pos', pos-step)
            b[:,pos:pos+step] = -98 + i
        b[:,intervals[-1]:] = -99 + len(intervals) 

    else:
        # Bathy Stepping for when hFacMin!=1
        #step = 5
        bathy_min = -112
        bathy_max = -104
        depths = np.linspace(bathy_min,bathy_max,xdim-2)
        print ('DEPTHS DIFF', depths)
        for i, pos in enumerate(depths):
            b[:,i+1] = depths[i] 
        b[:,0] = bathy_min 
        b[:,-1] = bathy_max
        # ---------------------------------------- #

    bathy.writeBin(b,name)
    plot_1d(bathy, name, xdim, ydim, title='bathy', fnum=0)

def plot_1d(data, data_dir, xdim, ydim, title='',fnum=0):
    y = data.readBin(data_dir,int(xdim),int(ydim))
    fig = plt.figure(fnum)
    p = plt.plot(y[0])
    plt.axis('equal')
    plt.title(title)

def plot_2d(state, data_dir, xdim, ydim, zdim, title='', fnum=0):
    y = state.readBin(data_dir,int(xdim), int(ydim), int(zdim))
    fig = plt.figure(fnum)
    p = plt.pcolormesh(y[:,:,0])
    plt.axis('equal')
    plt.colorbar(p)
    plt.title(title)
    
 

def make_wind():
    wind_name = case_name + '_wind.bin'
    #print wind_name
    w = Wind()
    #w.ydim = 144
    #w.wind()
    w.shrunk_wind()
    wind = w.get_wind() #wind = np.hstack( (wind,np.zeros((288,144))) )
    #wind = np.hstack( (wind,-wind) )
    #wind = wind - wind.min()
    
    #wind = w.readBin(wind_name, xdim, ydim)
    #w.plot_single(wind)
    #wind[:,144:] = np.zeros((288,144))
    #w.plot_num = 1

    w.writeBin(wind, wind_name)
    wind = w.readBin(wind_name, int(ydim), int(xdim))
    w.case = '001'
    plt.figure(101)
    p = plt.pcolormesh(wind)
    plt.colorbar(p)
    #plt.figure(100)
    #plt.plot(wind[0,:])
    plt.show()

def make_rbcs():
    mask_name = case_name + '_rbcs_mask.bin'
    t_name = case_name + '_rbcs_temp.bin'
    s_name = case_name + '_rbcs_salt.bin'
    mesh = np.mgrid[0:int(zdim),0:int(ydim),0:int(xdim)][0] 
    mesh = mesh + 1 
    
    print (bathy.writePath)
    rbcs_mask = np.where(mesh >= -b, 1.0, 0.0) 
    mask_args = np.argmax(rbcs_mask, axis=0)
    d = np.arange(100)
    fig = plt.figure(1)
    for i, frac in enumerate(np.logspace(-2,0,10,endpoint=False)[::-1]):
        print (frac)
        rbcs_mask[mask_args - i,:, d] = frac
    rbcs_t = np.full_like(rbcs_mask, -1.96226)
    rbcs_s = np.full_like(rbcs_mask, 34.5714)
    print ('shap', rbcs_mask.max())
    print ('shap', rbcs_mask.min())

    bathy.writeBin(rbcs_mask, mask_name)
    bathy.writeBin(rbcs_t, t_name)
    bathy.writeBin(rbcs_s, s_name)
    y = bathy.readBin(mask_name, int(xdim),int(ydim),int(zdim))
    fig = plt.figure(1)
    p = plt.pcolormesh(y[:,0,:])
    plt.axis('equal')
    plt.colorbar(p)
    plt.title('mask')

make_bathy()
make_ini_shice_topo()
make_ini_shice_p()
make_ini_vels()
