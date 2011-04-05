"""
==================================================
Using Camino for structural connectivity analysis
==================================================

Introduction
============

This script, connectivity_tutorial.py, demonstrates the ability to perform connectivity mapping
using Nipype for pipelining, Freesurfer for Reconstruction / Parcellation, Camino for tensor-fitting and tractography,
and the Connectome Mapping Toolkit (CMTK) for connectivity analysis.

    python connectivity_tutorial.py

We perform this analysis using the FSL course data, which can be acquired from here:
http://www.fmrib.ox.ac.uk/fslcourse/fsl_course_data2.tar.gz

This pipeline also requires the Freesurfer directory for 'subj1' from the FSL course data.
To save time, this data can be downloaded from here:
    http://dl.dropbox.com/u/315714/subj1.zip?dl=1

Import necessary modules from nipype.
"""

import nipype.interfaces.io as nio           # Data i/o
import nipype.interfaces.utility as util     # utility
import nipype.pipeline.engine as pe          # pypeline engine
import nipype.interfaces.camino as camino
import nipype.interfaces.fsl as fsl
import nipype.interfaces.camino2trackvis as cam2trk
import nipype.interfaces.freesurfer as fs    # freesurfer
import nipype.interfaces.matlab as mlab      # how to run matlab
import nipype.interfaces.cmtk.cmtk as cmtk
import nipype.interfaces.cmtk.base as cmtkbase
import nibabel as nb
import os                                    # system functions

"""
We use the following functions to scrape the voxel and data dimensions of the input images. This allows the
pipeline to be flexible enough to accept and process images of varying size. The SPM Face tutorial
(spm_face_tutorial.py) also implements this inferral of voxel size from the data.
"""

def get_vox_dims(volume):
    import nibabel as nb
    if isinstance(volume, list):
        volume = volume[0]
    nii = nb.load(volume)
    hdr = nii.get_header()
    voxdims = hdr.get_zooms()
    return [float(voxdims[0]), float(voxdims[1]), float(voxdims[2])]

def get_data_dims(volume):
    import nibabel as nb
    if isinstance(volume, list):
        volume = volume[0]
    nii = nb.load(volume)
    hdr = nii.get_header()
    datadims = hdr.get_data_shape()
    return [int(datadims[0]), int(datadims[1]), int(datadims[2])]

fsl.FSLCommand.set_default_output_type('NIFTI')

"""
This needs to point to the freesurfer subjects directory (Recon-all must have been run on subj1 from the FSL course data)
Alternatively, the reconstructed subject data can be downloaded from: http://dl.dropbox.com/u/315714/subj1.zip
"""
# If there is already another example dataset with both DWI and a Freesurfer directory, we can switch this tutorial to use
# that instead...

fs_dir = os.path.abspath('/usr/local/freesurfer')
subjects_dir = os.path.abspath('freesurfer')

"""
This needs to point to the fdt folder you can find after extracting
http://www.fmrib.ox.ac.uk/fslcourse/fsl_course_data2.tar.gz
"""
data_dir = os.path.abspath('fsl_course_data/fdt/')
fs.FSCommand.set_default_subjects_dir(subjects_dir)
subject_list = ['subj1']

"""
Use infosource node to loop through the subject list and define the input files.
For our purposes, these are the diffusion-weighted MR image, b vectors, and b values.
"""
infosource = pe.Node(interface=util.IdentityInterface(fields=['subject_id']), name="infosource")
infosource.iterables = ('subject_id', subject_list)

info = dict(dwi=[['subject_id', 'data']],
            bvecs=[['subject_id','bvecs']],
            bvals=[['subject_id','bvals']])

"""
Use datasource node to perform the actual data grabbing.
Templates for the associated images are used to obtain the correct images.
"""
datasource = pe.Node(interface=nio.DataGrabber(infields=['subject_id'],
                                               outfields=info.keys()),
                     name = 'datasource')

datasource.inputs.template = "%s/%s"
datasource.inputs.base_directory = data_dir
datasource.inputs.field_template = dict(dwi='%s/%s.nii.gz')
datasource.inputs.template_args = info
datasource.inputs.base_directory = data_dir

"""
FreeSurferSource nodes are used to retrieve various image
files that are automatically generated by the recon-all process.
Here we use three, two of which are defined to return files for solely the left and right hemispheres.
"""
FreeSurferSource = pe.Node(interface=nio.FreeSurferSource(), name='fssource')
FreeSurferSource.inputs.subjects_dir = subjects_dir

FreeSurferSourceLH = pe.Node(interface=nio.FreeSurferSource(), name='fssourceLH')
FreeSurferSourceLH.inputs.subjects_dir = subjects_dir
FreeSurferSourceLH.inputs.hemi = 'lh'

FreeSurferSourceRH = pe.Node(interface=nio.FreeSurferSource(), name='fssourceRH')
FreeSurferSourceRH.inputs.subjects_dir = subjects_dir
FreeSurferSourceRH.inputs.hemi = 'rh'

"""
Since the data comes from the FSL course, we must convert it to a scheme file
for use in Camino
"""
fsl2scheme = pe.Node(interface=camino.FSL2Scheme(), name="fsl2scheme")
fsl2scheme.inputs.usegradmod = True

"""
Use FSL's Brain Extraction to create a mask from the b0 image
"""
b0Strip = pe.Node(interface=fsl.BET(mask = True), name = 'bet_b0')

"""
Use FSL's FLIRT function to coregister the b0 mask and the structural image.
A convert_xfm node is then used to obtain the inverse matrix.
FLIRT is used once again to apply the inverse transformation to the parcellated brain image.
"""
coregister = pe.Node(interface=fsl.FLIRT(dof=6), name = 'coregister')
coregister.inputs.cost = ('corratio')

convertxfm = pe.Node(interface=fsl.ConvertXFM(), name = 'convertxfm')
convertxfm.inputs.invert_xfm = True

inverse = pe.Node(interface=fsl.FLIRT(), name = 'inverse')
inverse.inputs.interp = ('nearestneighbour')

"""
A number of conversion operations are required to obtain NIFTI files from the FreesurferSource for each subject.
Nodes are used to convert the following:
    -Original structural image to NIFTI
    -Parcellated white matter image to NIFTI
    -Parcellated whole-brain image to NIFTI
    -Left and Right hemisphere surfaces to GIFTI (for visualization in ConnectomeViewer)
"""
mri_convert_Brain = pe.Node(interface=fs.MRIConvert(), name='mri_convert_Brain')
mri_convert_Brain.inputs.out_type = 'nii'
mri_convert_WMParc = pe.Node(interface=fs.MRIConvert(), name='mri_convert_WMParc')
mri_convert_WMParc.inputs.out_type = 'nii'
mri_convert_AparcAseg = pe.Node(interface=fs.MRIConvert(), name='mri_convert_AparcAseg')
mri_convert_AparcAseg.inputs.out_type = 'nii'
mris_convertLH = pe.Node(interface=fs.MRIsConvert(), name='mris_convertLH')
mris_convertLH.inputs.out_datatype = 'gii'
mris_convertRH = pe.Node(interface=fs.MRIsConvert(), name='mris_convertRH')
mris_convertRH.inputs.out_datatype = 'gii'

"""
An inputnode is used to pass the data obtained by the data grabber to the actual processing functions
"""
inputnode = pe.Node(interface=util.IdentityInterface(fields=['subject_id']), name='inputnode')
inputnode = pe.Node(interface=util.IdentityInterface(fields=["dwi", "bvecs", "bvals", "subject_id"]), name="inputnode")

"""
In this section we create the nodes necessary for diffusion analysis.
First, the diffusion image is converted to voxel order.
"""
image2voxel = pe.Node(interface=camino.Image2Voxel(), name="image2voxel")

"""
Second, diffusion tensors are fit to the voxel-order data.
"""
dtifit = pe.Node(interface=camino.DTIFit(),name='dtifit')

"""
Next, a lookup table is generated from the schemefile and the
signal-to-noise ratio (SNR) of the unweighted (q=0) data.
"""
dtlutgen = pe.Node(interface=camino.DTLUTGen(), name="dtlutgen")
dtlutgen.inputs.snr = 16.0
dtlutgen.inputs.inversion = 1

"""
In this tutorial we implement probabilistic tractography using the PICo algorithm.
PICo tractography requires an estimate of the fibre direction and a model of its uncertainty in each voxel;
this is produced using the following node.
"""
picopdfs = pe.Node(interface=camino.PicoPDFs(), name="picopdfs")
picopdfs.inputs.inputmodel = 'dt'

"""
Finally, tractography is performed. In this tutorial, we will use only 1 iteration for time-saving purposes.
"""
track = pe.Node(interface=camino.TrackPICo(), name="track")
track.inputs.iterations = 1

"""
Connectivity mapping in Camino can be very memory intensive. To deal with this, we add a "shredding" node
which removes roughly half of the tracts in the file.
"""
tractshred = pe.Node(interface=camino.TractShredder(), name='tractshred')
tractshred.inputs.offset = 0
tractshred.inputs.bunchsize = 2
tractshred.inputs.space = 1

"""
Here we create a connectivity mapping node using Camino.
For visualization, it can be beneficial to set a threshold for the minimum number of fiber connections
that are required for an edge to be drawn on the graph.
"""
conmap = pe.Node(interface=camino.Conmap(), name='conmap')
conmap.inputs.threshold = 100

"""
Currently, the best program for visualizing tracts is TrackVis. For this reason, a node is included to
convert the raw tract data to .trk format. Solely for testing purposes, another node is added to perform the reverse.
"""
camino2trackvis = pe.Node(interface=cam2trk.Camino2Trackvis(), name="camino2trk")
camino2trackvis.inputs.min_length = 30
camino2trackvis.inputs.voxel_order = 'LAS'
trk2camino = pe.Node(interface=cam2trk.Trackvis2Camino(), name="trk2camino")

"""
Tracts can also be converted to VTK and OOGL formats, for use in programs such as GeomView and Paraview,
using the following two nodes.
"""
vtkstreamlines = pe.Node(interface=camino.VtkStreamlines(), name="vtkstreamlines")
procstreamlines = pe.Node(interface=camino.ProcStreamlines(), name="procstreamlines")
procstreamlines.inputs.outputtracts = 'oogl'

"""
We can also produce a variety of scalar values from our fitted tensors. The following nodes generate the
fractional anisotropy and diffusivity trace maps and their associated headers.
"""
fa = pe.Node(interface=camino.FA(),name='fa')
trd = pe.Node(interface=camino.TrD(),name='trd')
#md = pe.Node(interface=camino.MD(),name='md')
analyzeheader_fa = pe.Node(interface=camino.AnalyzeHeader(),name='analyzeheader_fa')
analyzeheader_fa.inputs.datatype = 'double'
analyzeheader_trace = pe.Node(interface=camino.AnalyzeHeader(),name='analyzeheader_trace')
analyzeheader_trace.inputs.datatype = 'double'

"""
This section adds the new Connectome Mapping Toolkit nodes
These interfaces are experimental and may not function properly, or at all.
For this reason, the nodes have not been connected.
"""
roigen = pe.Node(interface=cmtk.ROIGen(), name="ROIGen")
#roigen.inputs.use_freesurfer_LUT = True
#roigen.inputs.freesurfer_dir = fs_dir

""" This line must point to the adapted lookup table given in the example data"""
roigen.inputs.LUT_file = '/home/erik/Dropbox/Code/forked/nipype/examples/FreeSurferColorLUT_adapted.txt'
creatematrix = pe.Node(interface=cmtk.CreateMatrix(), name="CreateMatrix")
""" This line must point to the resolution network file given in the example data"""
creatematrix.inputs.resolution_network_file = '/home/erik/Dropbox/Code/forked/nipype/examples/resolution83.graphml'

CFFConverter = pe.Node(interface=cmtkbase.CFFConverter(), name="CFFConverter")

"""
Here is one example case for using the Nipype Select utility.
As FreesurferSource outputs a list similar to: ['aparc+aseg.mgz','aparc.a2009s+aseg.mgz']
when asked for the 'aparc_aseg' output, we use a select node to pass the name of
only the 'aparc+aseg.nii' file to a Freesurfer NIFTI conversion node.
"""
selectaparc = pe.Node(interface=util.Select(), name="SelectAparcAseg")
selectaparc.inputs.index = 0 # Use 0 for aparc+aseg and 1 for aparc.a2009s+aseg

"""
Here we define a few nodes using the Nipype Merge utility.
These are useful for passing lists of the files we want packaged in our CFF file.
"""
giftiSurfaces = pe.Node(interface=util.Merge(2), name="GiftiSurfaces")
niftiVolumes = pe.Node(interface=util.Merge(3), name="NiftiVolumes")
tractFiles = pe.Node(interface=util.Merge(1), name="TractFiles")
gpickledNetworks = pe.Node(interface=util.Merge(1), name="NetworkFiles")

"""
Since we have now created all our nodes, we can now define our workflow and start making connections.
"""
mapping = pe.Workflow(name='mapping')

"""
First, we connect the input node to the early conversion functions.
"""
mapping.connect([(inputnode, FreeSurferSource,[("subject_id","subject_id")])])
mapping.connect([(inputnode, FreeSurferSourceLH,[("subject_id","subject_id")])])
mapping.connect([(inputnode, FreeSurferSourceRH,[("subject_id","subject_id")])])

mapping.connect([(inputnode, image2voxel, [("dwi", "in_file")]),
                       (inputnode, fsl2scheme, [("bvecs", "bvec_file"),
                                                ("bvals", "bval_file")]),

                       (image2voxel, dtifit,[['voxel_order','in_file']]),
                       (fsl2scheme, dtifit,[['scheme','scheme_file']])
                      ])
mapping.connect([(FreeSurferSource, mri_convert_WMParc,[('wmparc','in_file')])])
mapping.connect([(FreeSurferSource, mri_convert_Brain,[('brain','in_file')])])
mapping.connect([(FreeSurferSourceLH, mris_convertLH,[('pial','in_file')])])
mapping.connect([(FreeSurferSourceRH, mris_convertRH,[('pial','in_file')])])

"""
This section coregisters the diffusion-weighted and parcellated white-matter image.
"""
mapping.connect([(inputnode, b0Strip,[('dwi','in_file')])])
mapping.connect([(b0Strip, coregister,[('out_file','in_file')])])
mapping.connect([(mri_convert_Brain, coregister,[('out_file','reference')])])
mapping.connect([(coregister, convertxfm,[('out_matrix_file','in_file')])])
mapping.connect([(b0Strip, inverse,[('out_file','reference')])])
mapping.connect([(convertxfm, inverse,[('out_file','in_matrix_file')])])
mapping.connect([(mri_convert_WMParc, inverse,[('out_file','in_file')])])
mapping.connect([(inverse, conmap,[('out_file','roi_file')])])

"""
The tractography pipeline consists of the following nodes.
"""
mapping.connect([(b0Strip, track,[("mask_file","seed_file")])])
mapping.connect([(fsl2scheme, dtlutgen,[("scheme","scheme_file")])])
mapping.connect([(dtlutgen, picopdfs,[("dtLUT","luts")])])
mapping.connect([(dtifit, picopdfs,[("tensor_fitted","in_file")])])
mapping.connect([(picopdfs, track,[("pdfs","in_file")])])

#Memory errors were fixed by shredding tracts. ProcStreamlines now runs fine, but I am still unable to open the OOGl file in Geomview. Could someone else try this on their machine? (output file is around 1 gb!)
#mapping.connect([(tractshred, procstreamlines,[("shredded","in_file")])])

"""
The tractography is passed to the shredder in preparation for connectivity mapping.
"""
mapping.connect([(track, tractshred,[("tracked","in_file")])])
mapping.connect([(tractshred, conmap,[("shredded","in_file")])])

"""
Connecting the Fractional Anisotropy and Trace nodes is simple, as they obtain their input from the
tensor fitting.

This is also where our voxel- and data-grabbing functions come in. We pass these functions, along with
the original DWI image from the input node, to the header-generating nodes. This ensures that the files
will be correct and readable.
"""
mapping.connect([(dtifit, fa,[("tensor_fitted","in_file")])])
mapping.connect([(fa, analyzeheader_fa,[('fa','in_file')])])
mapping.connect([(inputnode, analyzeheader_fa,[(('dwi', get_vox_dims), 'voxel_dims'),
(('dwi', get_data_dims), 'data_dims')])])

mapping.connect([(dtifit, trd,[("tensor_fitted","in_file")])])
mapping.connect([(trd, analyzeheader_trace,[("trace","in_file")])])
mapping.connect([(inputnode, analyzeheader_trace,[(('dwi', get_vox_dims), 'voxel_dims'),
(('dwi', get_data_dims), 'data_dims')])])

"""
The output tracts are converted to trackvis format (and back). Here we also use the voxel- and data-grabbing
functions defined at the beginning of the pipeline.
"""
mapping.connect([(track, camino2trackvis, [('tracked','in_file')]),
                       (track, vtkstreamlines,[['tracked','in_file']]),
                       (camino2trackvis, trk2camino,[['trackvis','in_file']])
                      ])
mapping.connect([(inputnode, camino2trackvis,[(('dwi', get_vox_dims), 'voxel_dims'),
(('dwi', get_data_dims), 'data_dims')])])

#These lines are commented out the Camino mean diffusivity function appears to be broken.
#mapping.connect([(dtifit, md,[("tensor_fitted","in_file")])])
#mapping.connect([(md, analyzeheader2,[("md","in_file")])])

"""
Here the CMTK connectivity mapping nodes are connected.
"""
mapping.connect([(FreeSurferSource, selectaparc,[("aparc_aseg","inlist")])])
mapping.connect([(selectaparc, mri_convert_AparcAseg,[("out","in_file")])])
mapping.connect([(mri_convert_AparcAseg, roigen,[("out_file","aparc_aseg_file")])])
mapping.connect([(roigen, creatematrix,[("roi_file","roi_file")])])
mapping.connect([(roigen, creatematrix,[("dict_file","dict_file")])])
mapping.connect([(camino2trackvis, creatematrix,[("trackvis","tract_file")])])
mapping.connect([(creatematrix, gpickledNetworks,[("matrix_file","in1")])])

mapping.connect([(mris_convertLH, giftiSurfaces,[("converted","in1")])])
mapping.connect([(mris_convertRH, giftiSurfaces,[("converted","in2")])])


mapping.connect([(roigen, niftiVolumes,[("roi_file","in1")])])
mapping.connect([(inputnode, niftiVolumes,[("dwi","in2")])])
mapping.connect([(mri_convert_Brain, niftiVolumes,[("out_file","in3")])])

mapping.connect([(camino2trackvis, tractFiles,[("trackvis","in1")])])
"""
This block connects a number of the files to the CFF converter. We pass lists of the surfaces
and volumes that are to be included, as well as the tracts and the network itself.
"""
mapping.connect([(giftiSurfaces, CFFConverter,[("out","gifti_surfaces")])])
mapping.connect([(gpickledNetworks, CFFConverter,[("out","gpickled_networks")])])
#mapping.connect([(niftiVolumes, CFFConverter,[("out","nifti_volumes")])])
mapping.connect([(tractFiles, CFFConverter,[("out","tract_files")])])
mapping.connect([(inputnode, CFFConverter,[("subject_id","title")])])

"""
Finally, we create another higher-level workflow to connect our mapping workflow with the info and datagrabbing nodes
declared at the beginning. Our tutorial can is now extensible to any arbitrary number of subjects by simply adding
their names to the subject list and their data to the proper folders.
"""
connectivity = pe.Workflow(name="connectivity")
connectivity.base_dir = os.path.abspath('connectivity_tutorial')
connectivity.connect([
                    (infosource,datasource,[('subject_id', 'subject_id')]),
                    (datasource,mapping,[('dwi','inputnode.dwi'),
                                               ('bvals','inputnode.bvals'),
                                               ('bvecs','inputnode.bvecs')
                                               ]),
        (infosource,mapping,[('subject_id','inputnode.subject_id')])
                ])

"""
The following functions run the whole workflow and produce a .dot and .png graph of the processing pipeline.
"""
connectivity.run()
connectivity.write_graph()
"""
This outputted .dot graph can be converted to a vector image for use in figures via the following command-line function:
dot -Tps graph.dot > graph.eps
"""
