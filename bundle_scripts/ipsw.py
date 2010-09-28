#!/usr/bin/python
from optparse import OptionParser
import sys
import os
import os.path as path
import plistlib


class BundleParser:
	def __init__(self, bundleDir, ipswDir, outDir, verbose):
		self.bundleDir = bundleDir
		self.ipswDir = ipswDir
		self.outDir = outDir
		self.verbose = verbose
		

	def fileWithSuffix(self, filePath, suffix):
		if filePath.lower().endswith('.dmg'):
			filePath = filePath[:-4]
			suffix = suffix + '.dmg'
		return path.join(self.outDir, path.basename(filePath) + suffix)	
		

	def decrypt_file(self, filePath, iv, key):
		decrypt_cmd = "xpwntool %s %s -iv %s -k %s" % \
			(path.join(self.ipswDir, filePath), self.fileWithSuffix(filePath, '.dec'), iv, key)
		if self.verbose:
			print "Unpacking: '%s'" % decrypt_cmd
		os.system(decrypt_cmd)
		

	def patch_file(self, filePath, patchFile):
		patch_cmd = "bspatch %s %s %s" % \
			(self.fileWithSuffix(filePath, '.dec'), self.fileWithSuffix(filePath, '.dec.p'), path.join(self.bundleDir, patchFile))
		if self.verbose:
			print "Patching: '%s'" % patch_cmd
		os.system(patch_cmd)
		
	
	def diff_llb(self, patch):
		filePath = patch [ 'File' ]
		patchFile = patch [ 'Patch' ]
		encrypt_cmd = "xpwntool %s %s -t %s -x24k -iv %s -k %s" % \
			(self.fileWithSuffix(filePath, ".dec.ap"), self.fileWithSuffix(filePath, '.ap'), \
			path.join(self.ipswDir, filePath) , patch['IV'], patch['Key'])
		
		if self.verbose:
			print "Encrypting LLB: '%s'" % encrypt_cmd
		os.system(encrypt_cmd)
		
		diff_cmd = "bsdiff %s %s %s" % \
			(path.join(self.ipswDir, filePath), self.fileWithSuffix(filePath, '.ap'), path.join(self.bundleDir, patchFile))
	
		if self.verbose:
			print "Diffing LLB: '%s'" % diff_cmd
		os.system(diff_cmd)
		
		

	def diff_file(self, patch):
		filePath = patch['File']
		patchFile = patch['Patch']
		if path.basename(filePath).startswith('LLB'):
			self.diff_llb(patch)
			return 
		diff_cmd = "bsdiff %s %s %s" % \
			(self.fileWithSuffix(filePath, '.dec'), self.fileWithSuffix(filePath, '.dec.ap'), path.join(self.bundleDir, patchFile)) 

		if self.verbose:
			print "Diffing: '%s'" % diff_cmd
		os.system(diff_cmd)
		

	def decrypt_rootfs(self):
		key = self.infoPlist['RootFilesystemKey']
		dmg = self.infoPlist['RootFilesystem']
		
		vfdecrypt_cmd = "vfdecrypt -i %s -o %s -k %s" % \
			(path.join(self.ipswDir, dmg), self.fileWithSuffix(dmg, '.dec'), key)
			
		if self.verbose:
			print "vfdecrypt: '%s'" % vfdecrypt_cmd
		
		os.system(vfdecrypt_cmd)
		
		mount_cmd = "hdiutil attach %s" % self.fileWithSuffix(dmg, '.dec')
		
		if self.verbose:
			print "hdiutil: '%s'" % mount_cmd
			
		os.system(mount_cmd)
				

	def fspatch_extract_callback(self, patch):
		if not 'Patch' in patch:
			return
		filePath = patch['File']
		mountpoint = path.join('/Volumes', self.infoPlist['RootFilesystemMountVolume'])
		cp_cmd = "cp %s %s" % (path.join(mountpoint, filePath), self.fileWithSuffix(filePath, ""))
		
		if self.verbose:
			print "cp: '%s'" % cp_cmd
			
		os.system(cp_cmd)	
		

	def mount_ramdisk(self):
		firmwarePatches = self.infoPlist['FirmwarePatches']
		if not 'Restore Ramdisk' in firmwarePatches:
			return
		patch = firmwarePatches['Restore Ramdisk']
		filePath = patch['File']
		
		mount_cmd = "hdiutil attach %s" % self.fileWithSuffix(filePath, '.dec')
		
		if self.verbose:
			print "hdiutil: '%s'" % mount_cmd
			
		os.system(mount_cmd)

	def fwpatch_decrypt_callback(self, patch, patchKey):
		self.decrypt_file(patch['File'], patch['IV'], patch['Key'])
		if 'Patch' in patch:
			self.patch_file(patch['File'], patch['Patch'])	

	def foreach_fwpatch(self, callback):
		firmwarePatches = self.infoPlist['FirmwarePatches']
		for patchKey in firmwarePatches:
			patch = firmwarePatches[patchKey]
			callback(patch, patchKey)
			
	
	def foreach_fspatch(self, callback):			
		filesystemPatches = self.infoPlist['FilesystemPatches']
		for patchGroupKey in filesystemPatches:
			patchGroup = filesystemPatches[patchGroupKey]
			for patch in patchGroup:
				callback(patch)
				
				
	def rdpatch_extract_callback(self, patch):
		filePath = patch['File']
		mountpoint = path.join('/Volumes', self.infoPlist['RestoreRamdiskMountVolume'])
		cp_cmd = "cp %s %s" % (path.join(mountpoint, filePath), self.fileWithSuffix(filePath, ""))
		
		if self.verbose:
			print "cp: '%s'" % cp_cmd
			
		os.system(cp_cmd)	
		
	
	def foreach_rdpatch(self, callback):
		rdPatches = self.infoPlist['RamdiskPatches']
		for rdKey in rdPatches:
			patch = rdPatches[rdKey]
			callback(patch)
	
	
	def umount_all(self):
		for key in ['RestoreRamdiskMountVolume', 'RootFilesystemMountVolume']:
			mountpoint = path.join('/Volumes', self.infoPlist[key])
			
			umount_cmd = "hdiutil detach %s" % mountpoint
			
			if self.verbose:
				print "Unmount: '%s'" % umount_cmd
				
			os.system(umount_cmd)			
	

	def process_info_plist(self):
		self.infoPlist = plistlib.readPlist(path.join(self.bundleDir, 'Info.plist'))
		
		self.foreach_fwpatch(self.fwpatch_decrypt_callback)
		
		self.mount_ramdisk()
		
		self.foreach_rdpatch(self.rdpatch_extract_callback)
														
		self.decrypt_rootfs()
		
		self.foreach_fspatch(self.fspatch_extract_callback)

		self.umount_all()

	
	def create_patch_files(self):
		infoPlist = plistlib.readPlist(path.join(self.bundleDir, 'Info.plist'))
		firmwarePatches = infoPlist['FirmwarePatches']
                for patchKey in firmwarePatches:
			patch = firmwarePatches[patchKey]
			if 'Patch' in patch:
				self.diff_file(patch)
	
def main():
	parser = OptionParser()
	parser.add_option("-b", "--bundle", dest="bundle", help="Bundle directory to use", metavar="BUNDLE_DIR")
	parser.add_option("-i", "--ipsw", dest="ipsw", help="Unpacked IPSW directory", metavar="IPSW_DIR")
	parser.add_option("-o", "--out", dest="out", help="Output directory", metavar="OUT_DIR")
	parser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False, help="Verbose mode")
	parser.add_option("-c", "--create", dest="create", action="store_true", default=False, help="Create patch files from work dir")

	(opts, args) = parser.parse_args()
	requiredOpts = ['bundle', 'ipsw', 'out']
	for req in requiredOpts:
		if not opts.__dict__[req]:
			print "'%s' argument is mandatory!" % req
			exit(1)
	bundleParser = BundleParser( opts.bundle, opts.ipsw, opts.out, opts.verbose )
	if opts.create:
		bundleParser.create_patch_files()
	else:
		bundleParser.process_info_plist()

if __name__ == "__main__":
    main()
