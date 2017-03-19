#!/usr/bin/python

"""
Create a copy of file xyz under ther subdirectories iPad_Air_2_es_ES, iPhone_5_de_DE etc
as  iPad_Air_2_es_ES__xyz, iPhone_5_de_DE___xyz etc
"""

import argparse
import glob
import inspect
import os
import shutil
import sys
import tempfile
import time

g_defaultRoot = '/Users/bmlam/Desktop/TestAuto_screenshots'

def _dbx ( text ):
    sys.stdout.write( '  Debug(%s - Ln %d): %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 

def _infoTs ( text, withTS = False ):
	if withTS:
		print( '\n%s (Ln %d) %s' % ( time.strftime("%H:%M:%S"), inspect.stack()[1][2], text ) )
	else :
		print( '\nINFO (Ln %d) %s' % ( inspect.stack()[1][2], text ) )

def _errorExit ( text ):
    sys.stderr.write( '\nERROR raised from %s - Ln %d: %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 
    sys.exit(1)

def parseCmdLine() :
	parser = argparse.ArgumentParser()
	parser.add_argument( '-r', '--rootPath', help='the parent of the subdirectories. Default: %s' % g_defaultRoot
		, default= g_defaultRoot )

	result = parser.parse_args()
	return result

def main():
	argObject = parseCmdLine()	
	targetDir = tempfile.mkdtemp()
	#	_infoTs( "Output temp dir: %s" % targetDir, True )
	rootDir = argObject.rootPath
	_dbx( rootDir )
	cntFiles = 0
	for root, dirs, files in os.walk( rootDir ):
		subDir = os.path.basename( root )
		_dbx( subDir )
		for file in files:
			cntFiles += 1
			srcFilePath = os.path.join( root, file )
			tgtFilePath = os.path.join( targetDir, subDir + '__' + file )
			# _dbx( srcFilePath )
			# _dbx( tgtFilePath )
			shutil.copyfile( srcFilePath, tgtFilePath )
		
	_infoTs( "Files copied to '%s': %d" % ( targetDir, cntFiles), True )

main()
