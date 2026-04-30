import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import os 
import glob
import astroalign as aa

from astropy.io import fits
from astropy.stats import sigma_clip
import scipy
import astropy
#from astropy.modeling.functional_models import Sersic1D
#from astropy.modeling import models, fitting




def master_bias(list_bias, out_name ='', out_dir = '', overwrite = 1):
    #on ouvre le premier fichier de list_bias pour obtenir la forme de chaque master bias
    shape_bias =  np.shape(fits.getdata(list_bias[0]))
    n_bias = len(list_bias)
    print(f'il y a {n_bias} poses de bias dans la liste')
    # on initialise un tableau numpy à zeros qui va contenir l'ensemble des poses de bias individuelles
    master_bias_list = np.zeros([n_bias,shape_bias[0],shape_bias[1]]) 
    for b,i in zip(list_bias,range(n_bias)):
        master_bias_list[i,:,:]= fits.getdata(b)
    # le master bias contient, en chaque pixel, la mediane de la valeur de ce pixel dans chacune des poses de bias 
    #master_bias = scipy.stats.sigmaclip(master_bias_list, low=5, high=5, maxiters=5,axis=0,masked=False)
    master_bias, low, upp = scipy.stats.sigmaclip(master_bias_list, low=5, high=5)

    master_bias = np.nanmedian(master_bias_list,axis=0)
    if len(out_name)>0:
        ## on enregistre le master bias dans un nouveau fichier fits
        hdu = fits.PrimaryHDU(master_bias)
        hdu.writeto(out_dir + out_name, overwrite = overwrite)
        print(f'le master bias a été sauvé en {out_dir + out_name}')
    return master_bias, out_dir + out_name
   


def master_flat(list_flat, master_bias_name, out_name ='', out_dir = '', overwrite = 1):
    #on ouvre le premier 
    tmp = fits.getdata(list_flat[0])
    # on initialise le master flat 
    master_flat = np.zeros(np.shape(tmp)) 
    # ouvrir le master bias
    mb = fits.getdata(master_bias_name)
    for b in list_flat:
        exp = fits.open(b)[0].header['EXPTIME']
        #tmp = (fits.getdata(b)-mb)
        tmp = fits.getdata(b)-mb
        master_flat += tmp/np.median(tmp)/len(list_flat)
    ## on normalise le resultat
    master_flat /= np.median(master_flat)
    if len(out_name)>0:
        ## on enregistre le master bias dans un nouveau fichier fits
        hdu = fits.PrimaryHDU(master_flat)
        hdu.writeto(out_dir + out_name, overwrite = overwrite)
    return master_flat


def stacking(list_files, master_bias_name, master_flat_name, out_name = '', out_dir = '', overwrite = 1):
    mb = fits.getdata(master_bias_name)
    mf = fits.getdata(master_flat_name)
    tmp = fits.getdata(list_files[0])
    image_concat = np.zeros([len(list_files),np.shape(tmp)[0],np.shape(tmp)[1]])
    for image,i in zip(list_files,range(len(list_files))):
        if (i==1):
            source = (fits.getdata(image)-mb)/mf # calibration
            source /= np.median(source) #renormalization
            #source =  np.array(fits.getdata(image), dtype="<f4")
            image_concat[i,:,:]=(source)#/mf
        elif (i>1):
            #registered_image, footprint = aa.register(np.array(fits.getdata(image), dtype="<f4"),source)   
            image = (fits.getdata(image)-mb)/mf
            image /= np.median(image)
            registered_image, footprint = aa.register(image,source, min_area=12)
            image_concat[i,:,:] = (registered_image)
    filtered_data = sigma_clip(image_concat, sigma=2, maxiters=10,axis=0,masked=False) #image_concat#

    final_image = np.nanmean(filtered_data, axis=0)
    final_image=(final_image).astype(np.float32)
    hdu = fits.PrimaryHDU(final_image)
    hdu.writeto(out_dir + out_name, overwrite=True)
    return final_image,out_dir + out_name

