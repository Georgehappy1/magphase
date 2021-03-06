# -*- coding: utf-8 -*-
"""
Created on Thu Dec 17 02:48:28 2015

My personal library for general audio processing.

@author: Felipe Espic
"""
import numpy as np
import os
from subprocess import call
import soundfile as sf
import libutils as lu
from scipy import interpolate
from ConfigParser import SafeConfigParser

MAGIC = -1.0E+10 # logarithm floor (the same as SPTK)

#-------------------------------------------------------------------------------
def parse_config():
    global _reaper_bin, _sptk_dir
    _curr_dir = os.path.dirname(os.path.realpath(__file__))

    _reaper_bin = os.path.realpath(_curr_dir + '/../tools/bin/reaper')
    _sptk_dir   = os.path.realpath(_curr_dir + '/../tools/bin')

    _config = SafeConfigParser()
    _config.read(_curr_dir + '/../config.ini')

    if not (_config.get('TOOLS', 'bin_dir')==''):
        _reaper_bin    = os.path.join(_config.get('TOOLS', 'bin_dir'), 'reaper')
        _sptk_dir      = _config.get('TOOLS', 'bin_dir')
    return
parse_config()



#-------------------------------------------------------------------------------
def gen_mask_simple(v_voi, nbins, cutoff_bin):
    '''
    Basically: 1=deterministic, 0=stochastic
    '''
    m_mask  = np.tile(v_voi, [nbins,1]).T
    m_mask[:,cutoff_bin:] = 0

    return m_mask

#------------------------------------------------------------------------------

def mix_by_mask(m_data_a, m_data_b, m_mask):
    '''
    Basically, in the mask: 1=deterministic, 0=stochastic
    Also: 1=m_data_a, 0=m_data_b
    '''
    m_data = m_mask * m_data_a + (1 - m_mask) * m_data_b

    return m_data

#------------------------------------------------------------------------------
def shift_to_pm(v_shift):
    v_pm = np.cumsum(v_shift)
    return v_pm

#------------------------------------------------------------------------------
def pm_to_shift(v_pm):
    v_shift = np.diff(np.hstack((0,v_pm)))
    return v_shift

#------------------------------------------------------------------------------
def gen_non_symmetric_win(left_len, right_len, win_func, b_norm=False):
    # Left window:
    v_left_win = win_func(1+2*left_len)
    v_left_win = v_left_win[0:(left_len+1)]
    
    # Right window:
    v_right_win = win_func(1+2*right_len)
    v_right_win = np.flipud(v_right_win[0:(right_len+1)])
    
    # Constructing window:
    v_win = np.hstack((v_left_win, v_right_win[1:]))
    if b_norm:
        v_win = v_win / np.sum(v_win)

    return v_win
    
#------------------------------------------------------------------------------
# generated centered assymetric window:
# If totlen is even, it is assumed that the center is the first element of the second half of the vector.
# TODO: case win_func == None
def gen_centr_win(winlen_l, winlen_r, totlen, win_func=None, b_fill_w_bound_val=False):
   
    v_win_shrt = gen_non_symmetric_win(winlen_l, winlen_r, win_func)  
    win_shrt_len = len(v_win_shrt)
    
    nx_cntr  = np.floor(totlen / 2.0).astype(int)
    nzeros_l = nx_cntr - winlen_l    
    
    v_win = np.zeros(totlen)
    if b_fill_w_bound_val:
        v_win += v_win_shrt[0]

    v_win[nzeros_l:nzeros_l+win_shrt_len] = v_win_shrt
    return v_win

#------------------------------------------------------------------------------
def ola(m_frm, shift):
    shift = int(shift)
    nfrms, frmlen = m_frm.shape

    sig_len = (nfrms - 1) * shift + frmlen
    v_sig   = np.zeros(sig_len)
    strt    = 0
    for nxf in xrange(nfrms):

        # Add frames:
        v_sig[strt:(strt+frmlen)] += m_frm[nxf,:]
        strt += shift

    return v_sig

#------------------------------------------------------------------------------
def frm_list_to_matrix(l_frames, v_shift, nFFT):
    nFFThalf = nFFT / 2 + 1
    nfrms    = len(v_shift)
    m_frm    = np.zeros((nfrms, nFFT))
    for i in xrange(nfrms):

        # Debug:
        #print(i)

        rel_shift  = nFFThalf - v_shift[i] - 1
        m_frm[i,:] = frame_shift(l_frames[i], rel_shift, nFFT)  
    
    return m_frm

#------------------------------------------------------------------------------
def frame_shift(v_frm, shift, out_len):
    right_len = out_len - (shift + len(v_frm))
    v_frm_out = np.hstack(( np.zeros(shift) , v_frm, np.zeros(right_len)))
    return v_frm_out
    
#------------------------------------------------------------------------------
# "Cosine window": cos_win**2 = hannnig
# power: 1=> coswin, 2=> hanning
def cos_win(N):
    v_x   = np.linspace(0,np.pi,N)
    v_win = np.sin(v_x)
    return v_win

#------------------------------------------------------------------------------
def hz_to_bin(v_hz, nFFT, fs):    
    return v_hz * nFFT / float(fs)

def bin_to_hz(v_bin, nFFT, fs):         
    return v_bin * fs / float(nFFT)

#------------------------------------------------------------------------------
# m_sp_l: spectrum on the left. m_sp_r: spectrum on the right
# TODO: Processing fo other freq scales, such as Mel.
def spectral_crossfade(m_sp_l, m_sp_r, cut_off, bw, fs, freq_scale='hz', win_func=np.hanning):
    '''
    m_sp_l and m_sp_r could be float or complex.
    '''

    # Hz to bin:
    nFFThalf = m_sp_l.shape[1]
    nFFT     = (nFFThalf - 1) * 2    
    bin_l    = lu.round_to_int(hz_to_bin(cut_off - bw/2.0, nFFT, fs))
    bin_r    = lu.round_to_int(hz_to_bin(cut_off + bw/2.0, nFFT, fs))

    # Gen short windows:
    bw_bin       = bin_r - bin_l
    v_win_shrt   = win_func(2*bw_bin + 1)
    v_win_shrt_l = v_win_shrt[bw_bin:]
    v_win_shrt_r = v_win_shrt[:bw_bin+1]
    
    # Gen long windows:
    v_win_l = np.hstack((np.ones(bin_l),  v_win_shrt_l , np.zeros(nFFThalf - bin_r - 1)))
    v_win_r = np.hstack((np.zeros(bin_l), v_win_shrt_r , np.ones(nFFThalf - bin_r - 1)))
    
    # Apply windows:
    m_sp_l_win = m_sp_l * v_win_l[None,:]
    m_sp_r_win = m_sp_r * v_win_r[None,:]
    m_sp       = m_sp_l_win + m_sp_r_win
    
    return m_sp
    

#------------------------------------------------------------------------------
def rceps_to_min_phase_rceps(m_rceps):
    '''
    # m_rceps: Complete real cepstrum (length=nfft)
    '''
    nFFThalf = m_rceps.shape[1] / 2 + 1
    m_rceps[:,1:(nFFThalf-1)] *= 2

    return m_rceps[:nFFThalf]


#------------------------------------------------------------------------------
# nc: number of coeffs
# fade_to_total: ratio between the length of the fade out over the total ncoeffs
def spectral_smoothing_rceps(m_sp_log, nc_total=60, fade_to_total=0.2):
    '''
    m_sp_log could be in any base log or decibels.
    '''

    nc_fade = lu.round_to_int(fade_to_total * nc_total)

    # Adding hermitian half:
    m_sp_log_ext = add_hermitian_half(m_sp_log)

    # Getting Cepstrum:
    m_rceps = np.fft.ifft(m_sp_log_ext).real

    m_rceps_minph = rceps_to_min_phase_rceps(m_rceps)
    #v_ener_orig_rms = np.sqrt(np.mean(m_rceps_minph**2,axis=1))
    
    # Create window:
    v_win_shrt = np.hanning(2*nc_fade+3)
    v_win_shrt = v_win_shrt[nc_fade+2:-1]    
        
    # Windowing:    
    m_rceps_minph[:,nc_total:] = 0
    m_rceps_minph[:,nc_total-nc_fade:nc_total] *= v_win_shrt

    # Energy compensation:
    #v_ener_after_rms = np.sqrt(np.mean(m_rceps_minph**2,axis=1))
    #v_ener_fact      = v_ener_orig_rms / v_ener_after_rms
    #m_rceps_minph    = m_rceps_minph * v_ener_fact[:,None]
    
    # Go back to spectrum:
    nfft        = m_rceps.shape[1]
    m_sp_log_sm = np.fft.fft(m_rceps_minph, n=nfft).real
    m_sp_log_sm = remove_hermitian_half(m_sp_log_sm)
    #m_sp_sm = np.exp(m_sp_sm)
    
    return m_sp_log_sm

#------------------------------------------------------------------------------
def log(m_x):
    '''
    Protected log: Uses MAGIC number to floor the logarithm.
    '''    
    m_y = np.log(m_x) 
    m_y[np.isinf(m_y)] = MAGIC
    m_y[np.isnan(m_y)] = MAGIC
    return m_y    
    
#------------------------------------------------------------------------------
# out_type: 'compact' or 'whole'
def rceps(m_data, in_type='log', out_type='compact'):
    """
    in_type: 'abs', 'log' (any log base), 'td' (time domain).
    TODO: 'td' case not implemented yet!!
    """
    ncoeffs = m_data.shape[1]
    if in_type == 'abs':
        m_data = log(m_data)    
        
    m_data  = add_hermitian_half(m_data, data_type='magnitude')
    m_rceps = np.fft.ifft(m_data).real

    # Amplify coeffs in the middle:
    if out_type == 'compact':        
        m_rceps[:,1:(ncoeffs-2)] *= 2
        m_rceps = m_rceps[:,:ncoeffs]
    
    return m_rceps 

#------------------------------------------------------------------------------
# interp_type: e.g., 'linear', 'slinear', 'zeros'
def interp_unv_regions(m_data, v_voi, voi_cond='>0', interp_type='linear'):

    vb_voiced   = eval('v_voi ' + voi_cond)
    
    if interp_type == 'zeros':
        m_data_intrp = m_data * vb_voiced[:,None]

    else:
        v_voiced_nx = np.nonzero(vb_voiced)[0]
    
        m_strt_and_end_voi_frms = np.vstack((m_data[v_voiced_nx[0],:] , m_data[v_voiced_nx[-1],:]))        
        t_strt_and_end_voi_frms = tuple(map(tuple, m_strt_and_end_voi_frms))
        
        func_intrp  = interpolate.interp1d(v_voiced_nx, m_data[vb_voiced,:], bounds_error=False , axis=0, fill_value=t_strt_and_end_voi_frms, kind=interp_type)
        
        nFrms = np.size(m_data, axis=0)
        m_data_intrp = func_intrp(np.arange(nFrms))
    
    return m_data_intrp

#------------------------------------------------------------------------------

def true_envelope(m_sp, in_type='abs', ncoeffs=60, thres_db=0.1):
    '''
    in_type: 'abs', 'db', or 'log'
    TODO: Test cases 'db' and 'log'
    '''

    if in_type=='db':
        m_sp_db = m_sp
    elif in_type=='abs':
        m_sp_db = db(m_sp)
    elif in_type=='log':
        m_sp_db = (20.0 / np.log(10.0)) * m_sp

    m_sp_db_env = np.zeros(m_sp_db.shape)
    nFrms     = m_sp_db.shape[0]
    n_maxiter = 100

    for f in xrange(nFrms):
        v_sp_db = m_sp_db[f,:]
        for i in xrange(n_maxiter):
            v_sp_db_sm = spectral_smoothing_rceps(v_sp_db[None,:], nc_total=ncoeffs, fade_to_total=0.7)[0]

            # Debug:
            if False:
                from libplot import lp
                lp.figure(1)
                lp.plot(m_sp_db[f,:], '.-b')
                lp.plot(v_sp_db, '.-r')
                lp.plot(v_sp_db_sm, '.-g')
                lp.grid()

            if np.mean(np.abs(v_sp_db - v_sp_db_sm)) < thres_db:
                break

            v_sp_db = np.maximum(v_sp_db, v_sp_db_sm)

        m_sp_db_env[f,:] = v_sp_db_sm

    if in_type=='db':
        m_sp_env = m_sp_db_env
    elif in_type=='abs':
        m_sp_env = db(m_sp_db_env, b_inv=True)
    elif in_type=='log':
        m_sp_env = (np.log(10.0) / 20.0) * m_sp_db_env

    return m_sp_env

# Read audio file:-------------------------------------------------------------
def read_audio_file(filepath, **kargs):
    '''
    Wrapper function. For now, just to keep consistency with the library
    '''    
    return sf.read(filepath, **kargs)
    
# Write wav file:--------------------------------------------------------------
# The format is picked automatically from the file extension. ('WAV', 'FLAC', 'OGG', 'AIFF', 'WAVEX', 'RAW', or 'MAT5')
# v_signal be mono (TODO: stereo, comming soon), values [-1,1] are expected if no normalisation is selected.
def write_audio_file(filepath, v_signal, fs, norm=0.98):
    '''
    norm: If None, no normalisation is applied. If it is a float number,
          it is the target value (absolute) for the normalisation.
    '''
    
    # Normalisation:
    if norm is not None:
        v_signal = norm * v_signal / np.max(np.abs(v_signal)) # default
        
    # Write:    
    sf.write(filepath, v_signal, fs)
    
    return

#------------------------------------------------------------------------------
# data_type: 'magnitude', 'phase' or 'zeros' (for zero padding), 'complex'
def add_hermitian_half(m_data, data_type='mag'):
           
    if (data_type == 'mag') or (data_type == 'magnitude'):
        m_data = np.hstack((m_data , np.fliplr(m_data[:,1:-1])))
        
    elif data_type == 'phase':        
        m_data[:,0]  = 0            
        m_data[:,-1] = 0   
        m_data = np.hstack((m_data , -np.fliplr(m_data[:,1:-1])))

    elif data_type == 'zeros':
        nfrms, nFFThalf = m_data.shape
        m_data = np.hstack((m_data , np.zeros((nfrms,nFFThalf-2))))
        
    elif data_type == 'complex':
        m_data_real = add_hermitian_half(m_data.real)
        m_data_imag = add_hermitian_half(m_data.imag, data_type='phase')
        m_data      = m_data_real + m_data_imag * 1j
    
    return m_data

# Remove hermitian half of fft-based data:-------------------------------------
# Works for either even or odd fft lenghts.
def remove_hermitian_half(m_data):
    dp = lu.DimProtect(m_data)
    
    nFFThalf   = int(np.floor(np.size(m_data,1) / 2)) + 1
    m_data_rem = m_data[:,:nFFThalf].copy()

    dp.end(m_data_rem)
    return m_data_rem
    
#-----------------------------------------------------
def read_est_file(est_file):
    '''
    Generic function to read est files. So far, it reads the first two columns of est files. (TODO: expand)
    '''

    # Get EST_Header_End line number: (TODO: more efficient)
    with open(est_file) as fid:
        header_size = 1 # init
        for line in fid:
            if line == 'EST_Header_End\n':
                break
            header_size += 1

    m_data = np.loadtxt(est_file, skiprows=header_size, usecols=[0,1])
    return m_data

#------------------------------------------------------------------------------
# check_len_smpls= signal length. If provided, it checks and fixes for some pm out of bounds (REAPER bug)
# fs: Must be provided if check_len_smpls is given
def read_reaper_est_file(est_file, check_len_smpls=-1, fs=-1, skiprows=7, usecols=[0,1]):

    # Checking input params:
    if (check_len_smpls > 0) and (fs == -1):
        raise ValueError('If check_len_smpls given, fs must be provided as well.')

    # Read text: TODO: improve skiprows
    m_data = np.loadtxt(est_file, skiprows=skiprows, usecols=usecols)
    m_data = np.atleast_2d(m_data)
    v_pm_sec  = m_data[:,0]
    v_voi = m_data[:,1]

    # Protection against REAPER bugs 1:
    vb_correct = np.hstack(( True, np.diff(v_pm_sec) > 0))
    v_pm_sec  = v_pm_sec[vb_correct]
    v_voi = v_voi[vb_correct]

    # Protection against REAPER bugs 2 (maybe it needs a better protection):
    if (check_len_smpls > 0):
        v_pm_smpls = lu.round_to_int(v_pm_sec * fs)
        if ( v_pm_smpls[-1] >= (check_len_smpls-1) ):
            vb_correct_2 = v_pm_smpls < (check_len_smpls-1)
            v_pm_smpls = v_pm_smpls[vb_correct_2]
            v_pm_sec   = v_pm_sec[vb_correct_2]
            v_voi      = v_voi[vb_correct_2]

    return v_pm_sec, v_voi

# REAPER wrapper:--------------------------------------------------------------
def reaper(in_wav_file, out_est_file):
    print("Extracting epochs with REAPER...")
    global _reaper_bin
    cmd =  _reaper_bin + " -s -x 400 -m 50 -a -u 0.005 -i %s -p %s" % (in_wav_file, out_est_file)
    call(cmd, shell=True)
    return
    
#------------------------------------------------------------------------------
def f0_to_lf0(v_f0):
       
    old_settings = np.seterr(divide='ignore') # ignore warning
    v_lf0 = np.log(v_f0)
    np.seterr(**old_settings)  # reset to default
    
    v_lf0[np.isinf(v_lf0)] = MAGIC
    return v_lf0

# Get pitch marks from signal using REAPER:------------------------------------

def get_pitch_marks(v_sig, fs):
    
    temp_wav = lu.ins_pid('temp.wav')
    temp_pm  = lu.ins_pid('temp.pm')
        
    sf.write(temp_wav, v_sig, fs)
    reaper(temp_wav, temp_pm)
    v_pm = np.loadtxt(temp_pm, skiprows=7)
    v_pm = v_pm[:,0]
    
    # Protection against REAPER bugs 1:
    vb_correct = np.hstack(( True, np.diff(v_pm) > 0))
    v_pm = v_pm[vb_correct]
    
    # Protection against REAPER bugs 2 (maybe I need a better protection):
    if (v_pm[-1] * fs) >= (np.size(v_sig)-1):
        v_pm = v_pm[:-1]
    
    # Removing temp files:
    os.remove(temp_wav)
    os.remove(temp_pm)
    
    return v_pm


# Next power of two:-----------------------------------------------------------
def next_pow_of_two(x):
    # Protection:    
    if x < 2: 
        x = 2
    # Safer for older numpy versions:
    x = 2**np.ceil(np.log2(x)).astype(int)
    
    return x

#---------------------------------------------------------------------------
def windowing(v_sig, winlen, shift, winfunc=np.hanning, extend='none'):
    '''
    Typical constant frame rate windowing function
    winlen and shift (hopsize) in samples.
    extend: 'none', 'both', 'beg', 'end' . Extension of v_sig towards its beginning and/or end.
    '''
    shift = int(shift)
    vWin   = winfunc(winlen)
    frmLen = len(vWin)

    if extend=='both' or extend=='beg':
        nZerosBeg = int(np.floor(frmLen/2))
        vZerosBeg = np.zeros(nZerosBeg)
        v_sig     = np.concatenate((vZerosBeg, v_sig))

    if extend=='both' or extend=='end':
        nZerosEnd = frmLen
        vZerosEnd = np.zeros(nZerosEnd)
        v_sig     = np.concatenate((v_sig, vZerosEnd))

    nFrms  = np.floor(1 + (v_sig.shape[0] - winlen) / float(shift)).astype(int)
    mSig   = np.zeros((nFrms, frmLen))
    nxStrt = 0
    for t in xrange(nFrms):
        #print(t)
        mSig[t,:] = v_sig[nxStrt:(nxStrt+frmLen)] * vWin
        nxStrt = nxStrt + shift   
    
    return mSig

# This function is provided to to avoid confusion about how to compute the exact 
# number of frames from shiftMs and fs    
def GetNFramesFromSigLen(sigLen, shiftMs, fs):
    
    shift = np.round(fs * shiftMs / 1000)
    nFrms = np.ceil(1 + ((sigLen - 1) / shift))
    nFrms = int(nFrms)
    
    return nFrms


#==============================================================================
# Converts mcep to lin sp, without doing any  Mel warping.
def mcep_to_lin_sp_log(mgc_mat, nFFT):
    
    nFrms, n_coeffs = mgc_mat.shape
    nFFTHalf = 1 + nFFT/2
    
    mgc_mat = np.concatenate((mgc_mat, np.zeros((nFrms, (nFFT/2 - n_coeffs + 1)))),1)
    mgc_mat = np.concatenate((mgc_mat, np.fliplr(mgc_mat[:,1:-1])),1)
    sp_log  = (np.fft.fft(mgc_mat, nFFT,1)).real
    sp_log  = sp_log[:,0:nFFTHalf]

    return sp_log 

    
#Gets RMS from matrix no matter the number of bins m_data has, 
#it figures out according to the FFT length.
# For example, nFFT = 128 , nBins_data= 60 (instead of 65 or 128)
def get_rms(m_data, nFFT):
    m_data2 = m_data**2
    m_data2[:,1:(nFFT/2)] = 2 * m_data2[:,1:(nFFT/2)]    
    v_rms = np.sqrt(np.sum(m_data2[:,0:(nFFT/2+1)],1) / nFFT)    
    return v_rms   
    
# Converts spectrum to MCEPs using SPTK toolkit--------------------------------  
# if alpha=0, no spectral warping
# m_sp: absolute and non redundant spectrum
# in_type: Type of input spectrum. if 3 => |f(w)|. If 1 => 20*log|f(w)|. If 2 => ln|f(w)|
# fft_len: If 0 => automatic computed from input data, If > 0 , is the value of the fft length
def sp_to_mcep(m_sp, n_coeffs=60, alpha=0.77, in_type=3, fft_len=0):

    #Pre:
    temp_sp  =  lu.ins_pid('temp.sp')
    temp_mgc =  lu.ins_pid('temp.mgc')
    
    # Writing input data:
    lu.write_binfile(m_sp, temp_sp)

    if fft_len is 0: # case fft automatic
        fft_len = 2*(np.size(m_sp,1) - 1)

    # MCEP:
    sptk_mcep_bin = os.path.join(_sptk_dir, 'mcep')
    curr_cmd = sptk_mcep_bin + " -a %1.2f -m %d -l %d -e 1.0E-8 -j 0 -f 0.0 -q %d %s > %s" % (alpha, n_coeffs-1, fft_len, in_type, temp_sp, temp_mgc)
    call(curr_cmd, shell=True)
    
    # Read MGC File:
    m_mgc = lu.read_binfile(temp_mgc , n_coeffs)
    
    # Deleting temp files:
    os.remove(temp_sp)
    os.remove(temp_mgc)
    
    #$sptk/mcep -a $alpha -m $mcsize -l $nFFT -e 1.0E-8 -j 0 -f 0.0 -q 3 $sp_dir/$sentence.sp > $mgc_dir/$sentence.mgc
    
    return m_mgc

#============================================================================== 
# out_type: 'db', 'log', 'abs' (absolute)    
def mcep_to_sp_cosmat(m_mcep, n_spbins, alpha=0.77, out_type='abs'):
    '''
    mcep to sp using dot product with cosine matrix.
    '''
    # Warping axis:
    n_cepcoeffs = m_mcep.shape[1]
    v_bins_out  = np.linspace(0, np.pi, num=n_spbins)
    v_bins_warp = np.arctan(  (1-alpha**2) * np.sin(v_bins_out) / ((1+alpha**2)*np.cos(v_bins_out) - 2*alpha) ) 
    v_bins_warp[v_bins_warp < 0] += np.pi
    
    # Building matrix:
    m_trans = np.zeros((n_cepcoeffs, n_spbins))
    for nxin in xrange(n_cepcoeffs):
        for nxout in xrange(n_spbins):
            m_trans[nxin, nxout] = np.cos( v_bins_warp[nxout] * nxin )        
            
    # Apply transformation:
    m_sp = np.dot(m_mcep, m_trans)
    
    if out_type == 'abs':
        m_sp = np.exp(m_sp)
    elif out_type == 'db':
        m_sp = m_sp * (20 / np.log(10))
    elif out_type == 'log':
        pass
    
    return m_sp

# Absolute to Decibels:--------------------------------------------------------
# b_inv: inverse function
def db(m_data, b_inv=False):
    if b_inv==False:
        return 20 * np.log10(m_data) 
    elif b_inv==True:
        return 10 ** (m_data / 20)

            
# in_type: Type of input spectrum. if 3 => |f(w)|. If 1 => 20*log|f(w)|. If 2 => ln|f(w)|        
def sp_mel_warp(m_sp, nbins_out, alpha=0.77, in_type=3):
    '''
    Info:
    in_type: Type of input spectrum. if 3 => |f(w)|. If 1 => 20*log|f(w)|. If 2 => ln|f(w)|        
    '''
    
    # sp to mcep:
    m_mcep = sp_to_mcep(m_sp, n_coeffs=nbins_out, alpha=alpha, in_type=in_type)
    
    # mcep to sp:
    if in_type == 3:
        out_type = 'abs'
    elif in_type == 1:
        out_type = 'db'
    elif in_type == 2:
        out_type = 'log'
        
    m_sp_wrp = mcep_to_sp_cosmat(m_mcep, nbins_out, alpha=0.0, out_type=out_type)
    return m_sp_wrp
    

#==============================================================================
# in_type: 'abs', 'log'
# TODO: 'db'
def sp_mel_unwarp(m_sp_mel, nbins_out, alpha=0.77, in_type='log'):
    
    ncoeffs = m_sp_mel.shape[1]
    
    if in_type == 'abs':
        m_sp_mel = np.log(m_sp_mel)
    
    #sp to mcep:
    m_sp_mel = add_hermitian_half(m_sp_mel, data_type='magnitude')
    m_mcep   = np.fft.ifft(m_sp_mel).real
    
    # Amplify coeffs in the middle:    
    m_mcep[:,1:(ncoeffs-2)] *= 2
       
    #mcep to sp:    
    m_sp_unwr = mcep_to_sp_cosmat(m_mcep[:,:ncoeffs], nbins_out, alpha=alpha, out_type=in_type)
    
    return m_sp_unwr


def convert_label_state_align_to_var_frame_rate(in_lab_st_file, v_dur_state, out_lab_st_file):
    # Constants:
    shift_ms = 5.0

    # Read input files:
    mstr_labs_st = np.loadtxt(in_lab_st_file, dtype='string', delimiter=" ", comments=None, usecols=(2,))

    v_dur_ms = v_dur_state * shift_ms
    v_dur_ns = v_dur_ms * 10000
    v_dur_ns = np.hstack((0,v_dur_ns))
    v_dur_ns_cum = np.cumsum(v_dur_ns)
    m_dur_ns_cum = np.vstack((v_dur_ns_cum[:-1], v_dur_ns_cum[1:])).T.astype(int)

    # To string array:
    mstr_dur_ns_cum = np.char.mod('%d', m_dur_ns_cum)

    # Concatenate data:
    mstr_out_labs_st = np.hstack((mstr_dur_ns_cum, mstr_labs_st[:,None]))

    # Save file:
    np.savetxt(out_lab_st_file, mstr_out_labs_st,  fmt='%s')
    return


def build_mel_curve(alpha, nbins, amp=np.pi):
    v_bins  = np.linspace(0, np.pi, nbins)
    v_bins_warp = np.arctan(  (1-alpha**2) * np.sin(v_bins) / ((1+alpha**2)*np.cos(v_bins) - 2*alpha) )
    v_bins_warp[v_bins_warp < 0] += np.pi

    v_bins_warp = v_bins_warp * (amp/np.pi)

    return v_bins_warp


def apply_fbank(m_mag, v_bins_warp, nbands, win_func=np.hanning, mode='average'):
    '''
    Applies an average filter bank.
    nbands: number of output bands.
    v_bins_warp: Mapping from input bins to output (monotonically crescent from 0 to any positive number).
                 Requirement: length = m_mag.shape[1]. If wanted, use build_mel_curve(...) to construct it.
    '''
    nfrms, nbins = m_mag.shape

    # Bands gen:
    maxval = v_bins_warp[-1]
    v_cntrs_mel = np.linspace(0, maxval, nbands)

    # To linear frequency:
    f_interp = interpolate.interp1d(v_bins_warp, np.arange(nbins), kind='quadratic')
    v_cntrs  = lu.round_to_int(f_interp(v_cntrs_mel))

    # Build filter bank:
    m_fbank = np.zeros((nbins, nbands))
    v_cntrs_ext = np.r_[v_cntrs[0], v_cntrs, v_cntrs[-1]]
    v_winlen = np.zeros(nbands)
    for nxb in xrange(1, nbands+1):
        winlen_l = v_cntrs_ext[nxb]   - v_cntrs_ext[nxb-1]
        winlen_r = v_cntrs_ext[nxb+1] - v_cntrs_ext[nxb]
        v_win    = gen_non_symmetric_win(winlen_l, winlen_r, win_func=win_func, b_norm=True)
        winlen   = v_win.size
        v_winlen[nxb-1] = winlen
        m_fbank[v_cntrs_ext[nxb-1]:(v_cntrs_ext[nxb-1]+winlen),nxb-1] = v_win

    # Apply filterbank:
    if mode=='average':
        m_mag_mel = np.dot(m_mag, m_fbank)
    elif mode=='maxabs':
        m_mag_mel = np.zeros((nfrms, nbands))
        for nxf in xrange(nfrms):
            v_mag = m_mag[nxf,:]
            m_filtered = v_mag[:,None] * m_fbank
            v_nx_max   = np.argmax(np.abs(m_filtered), axis=0)
            m_mag_mel[nxf,:]  = v_mag[v_nx_max]

    return m_mag_mel, v_winlen

def sp_mel_warp_fbank(m_mag, n_melbands, alpha=0.77):

    nfrms, nbins = m_mag.shape
    v_bins_warp  = build_mel_curve(alpha, nbins)
    m_mag_mel = np.exp(apply_fbank(log(m_mag), v_bins_warp, n_melbands)[0])

    return m_mag_mel

def sp_mel_warp_fbank_2d(m_mag, n_melbands, alpha=0.77):
    '''
    It didn't work as expected.
    '''

    nfrms, nbins  = m_mag.shape
    v_bins_warp   = build_mel_curve(alpha, nbins)
    m_mag_mel_log, v_winlen = apply_fbank(log(m_mag), v_bins_warp, n_melbands)

    # Fixing boundaries in window lengths:
    #v_winlen[0] = v_winlen[1]
    #v_winlen[-1] = v_winlen[-2]


    #max_span = 5
    #v_td_span = (v_winlen - v_winlen[0])
    #v_td_span = (max_span - 1.0) * v_td_span / v_td_span[-1] + 1

    '''
    v_winlen_norm = v_winlen / nbins
    td_factor = 20
    v_td_span = td_factor * v_winlen_norm
    v_td_span = 2 * np.ceil(v_td_span / 2.0) - 1 # Ensuring odd numbers.
    v_td_span = np.maximum(v_td_span, 1.0)
    v_td_span = v_td_span.astype(int)
    '''
    max_span = 5
    v_td_span = 1 + build_mel_curve(-0.3, n_melbands, amp=(max_span - 1.0))
    v_td_span = (2 * np.ceil(v_td_span / 2.0) - 1).astype(int) # Ensuring odd numbers.


    m_mag_mel_log_2d = np.zeros(m_mag_mel_log.shape)
    for nxb in xrange(v_td_span.size):
        m_mag_mel_log_2d[:,nxb] = smooth_by_conv(m_mag_mel_log[:,nxb], v_win=np.hanning(v_td_span[nxb] + 2))


    if False:
        plm(m_mag_mel_log[:,:])
        plm(m_mag_mel_log_2d[:,:])

        pl(v_td_span)

    return np.exp(m_mag_mel_log_2d)

def sp_mel_unwarp_fbank(m_mag_mel, nbins, alpha=0.77):

    #nfrms, n_melbands = m_mag_mel.shape

    # All of this to compute v_cntrs. It could be coded much more efficiently.----------------------
    # Bins warping:
    #v_bins  = np.linspace(0, np.pi, num=nbins)
    #v_bins_warp = np.arctan(  (1-alpha**2) * np.sin(v_bins) / ((1+alpha**2)*np.cos(v_bins) - 2*alpha) )
    #v_bins_warp[v_bins_warp < 0] += np.pi
    v_bins_warp = build_mel_curve(alpha, nbins, amp=np.pi)
    m_mag = unwarp_from_fbank(m_mag_mel, v_bins_warp)

    '''
    # Bands gen:
    maxval = v_bins_warp[-1]
    v_cntrs_mel = np.linspace(0, maxval, n_melbands)

    # To linear frequency:
    f_interp  = interpolate.interp1d(v_bins_warp, np.arange(nbins), kind='quadratic')
    v_cntrs   = lu.round_to_int(f_interp(v_cntrs_mel))
    #--------------------------------------------------------------------------------------------------

    v_bins = np.arange(nbins)
    m_mag = np.zeros((nfrms, nbins))
    for nxf in xrange(nfrms):
        f_interp = interpolate.interp1d(v_cntrs, m_mag_mel[nxf,:], kind='quadratic')
        #f_interp = interpolate.interp1d(v_cntrs, m_mag_mel[nxf,:], kind='linear')
        m_mag[nxf,:] = f_interp(v_bins)
    '''

    return m_mag


def unwarp_from_fbank(m_mag_mel, v_bins_warp, interp_kind='quadratic'):
    '''
    n_bins: number of frequency bins (i.e., Hz).
    v_bins_warp: Mapping from input bins to output (monotonically crescent from 0 to any positive number).
                 Requirement: length = m_mag.shape[1]. If wanted, use build_mel_curve(...) to construct it.
    '''

    nfrms, n_melbands = m_mag_mel.shape
    n_bins = v_bins_warp.size

    # Bands gen:
    maxval = v_bins_warp[-1]
    v_cntrs_mel = np.linspace(0, maxval, n_melbands)

    # To linear frequency:
    f_interp  = interpolate.interp1d(v_bins_warp, np.arange(n_bins), kind=interp_kind)
    v_cntrs   = lu.round_to_int(f_interp(v_cntrs_mel))

    # Process per frame:
    v_bins = np.arange(n_bins)
    m_mag = np.zeros((nfrms, n_bins))
    for nxf in xrange(nfrms):
        f_interp = interpolate.interp1d(v_cntrs, m_mag_mel[nxf,:], kind=interp_kind)
        #f_interp = interpolate.interp1d(v_cntrs, m_mag_mel[nxf,:], kind='linear')
        m_mag[nxf,:] = f_interp(v_bins)

    return m_mag

#-------------------------------------------------------------------------------------------------------
# 2-D Smoothing by convolution: (from ScyPy Cookbook - not checked yet!)-----------------------------
def smooth_by_conv(m_data, v_win=np.hanning(11)):
    '''
    Smooths along m_data columns. If m_data is 1d, it smooths along the other dimension.
    Length of v_win should be odd.
    '''

    def smooth_by_conv_1d(v_data, v_win=np.hanning(11)):
        """smooth the data using a window with requested size.

        TODO: the window parameter could be the window itself if an array instead of a string
        NOTE: length(output) != length(input), to correct this: return y[(win_len/2-1):-(win_len/2)] instead of just y.
        """
        win_len = v_win.size
        if v_data.ndim != 1:
            raise ValueError, "smooth only accepts 1 dimension arrays."
        if v_data.size < win_len:
            raise ValueError, "Input vector needs to be bigger than window size."

        if win_len<3:
            return v_data

        half_win_len = (win_len-1)/2
        v_data_ext   = np.r_[ v_data[0]+np.zeros(half_win_len), v_data, v_data[-1]+np.zeros(half_win_len)]

        v_data_smth = np.convolve(v_win/v_win.sum(), v_data_ext, mode='valid')

        #v_data_smth2 = v_data_smth[half_win_len:-half_win_len]
        #s=np.r_[v_data[win_len-1:0:-1],v_data,v_data[-1:-win_len:-1]]

        #y=np.convolve(v_win/v_win.sum(),s,mode='valid')
        return v_data_smth

    if m_data.ndim==1:
        return smooth_by_conv_1d(m_data, v_win=v_win)

    m_data_smth = np.zeros((m_data.shape))
    ncols = m_data.shape[1]
    for nxc in xrange(ncols):
        m_data_smth[:,nxc] = smooth_by_conv_1d(m_data[:,nxc], v_win=v_win)

    return m_data_smth

def build_min_phase_from_mag_spec(m_mag):

    fft_len_half = m_mag.shape[1]
    m_mag_log = log(m_mag)
    m_mag_log = add_hermitian_half(m_mag_log)
    m_ceps    = np.fft.ifft(m_mag_log).real

    m_ceps_min_ph = m_ceps
    m_ceps_min_ph[:,fft_len_half:] = 0.0
    m_ceps_min_ph[:,1:(fft_len_half-1)] *= 2.0
    m_mag_cmplx_min_ph = np.fft.fft(m_ceps_min_ph)
    m_mag_cmplx_min_ph = remove_hermitian_half(m_mag_cmplx_min_ph)
    m_mag_cmplx_min_ph = np.exp(m_mag_cmplx_min_ph)

    return m_mag_cmplx_min_ph

