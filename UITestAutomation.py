#!/usr/bin/python

"""
Originally based on Jonathan Penn's screenshooter for test automation and adopted 
to work with Apple's test automation framework. Also courtesy some third party tools
prominenty by zmeyc to make screenshots and delaying work

Tasks performed by this script ( _IDEALLY_ ):
	* xcodebuild the app bundle
	* Determine the simulatedDevice
	* Fire up instruments to deploy the build app bundle to the targeted Simulator, passing along the UI automation script
	* instruments plays the automation script which also takes screen shots as .png files saved in the location given by "-e UIARESULTSPATH". However instruments seems to remember the run number and always create a new subfolder per run.
	* Copy the png files from the given location to a more "persistent" location, creating a folder whose name includes the the device type, locale and language

In practice in my test and trial approach the current sequence is chosen sicne it SHOULD work:
	* xcodebuild the app bundle
	* iterate over target dvices
	* 	iterate over target languages
	* 		xcrun to install the app to the target dvice with the target app
	* 		xcodebuild to fire the UI test target (which exercise the test cases and make screenshots )
	* 		save the taken screenshots to the appropiate subdirectory based on device and language

Some coding convention to bear in mind:
	assignment: always leave space to both side of = to be consistent with swift. Named argument in method calls may be exception
"""

import argparse 
import glob 
import inspect 
import os 
import re
import shutil
import subprocess 
import sys 
import time 

g_screenshotsBakRoot=  os.path.join( os.environ[ 'HOME' ] , 'Desktop',  'TestAuto_screenshots' )
g_bundleDir			= "" # set later
g_traceResultsDir	= "" # set later

g_cntDisplayed = 0

def _dbx ( text ):
    sys.stdout.write( '  Debug(%s - Ln %d): %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 

def _infoTs ( text, withTS = False ):
	if withTS:
		print( '%s (Ln %d) %s' % ( time.strftime("%H:%M:%S"), inspect.stack()[1][2], text ) )
	else :
		print( 'INFO (Ln %d) %s' % ( inspect.stack()[1][2], text ) )

def _errorExit ( text ):
    sys.stderr.write( 'ERROR raised from %s - Ln %d: %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 
    sys.exit(1)

def parseCmdLine() :
	buildOutputLoc	= os.path.join( "/tmp", "UITestAutomatationOutput" )

	parser = argparse.ArgumentParser()
	# lowercase shortkeys

	parser.add_argument( '-o', '--BuildTestOutput', help='build and test output location for xcodebuild', default= buildOutputLoc )
	parser.add_argument( '-p', '--project_dir', help='Top level directory where xcode project file resides', default = '..' )
	parser.add_argument( '-s', '--screenshotsArchiveRoot', help='root location for screenshots. Subfolders based on device and lang will be created', default=g_screenshotsBakRoot )

	cleanSwithGroup = parser.add_mutually_exclusive_group(required=False)
	cleanSwithGroup.add_argument('-C', '--clean', dest='cleanSwitch', action='store_true')
	cleanSwithGroup.add_argument('-c', '--no-clean', dest='cleanSwitch', action='store_false')
	parser.set_defaults(cleanSwitch=True)

	result= parser.parse_args()

	global g_bundleDir
	g_bundleDir			= "%s/app.app" %  buildOutputLoc

	for (k, v) in vars( result ).iteritems () : _dbx( "%s : %s" % (k, v) )

	return result

def getListOfLangsAndDevicesFromFile(filePath):
	"""Decompose the file content into list of languages and device types 
	"""

	fieldSep = ':'
	langLiteral = 'lang'
	devLiteral  = 'dev'

	try :
		fh= open( filePath, 'r')
	except IOError:
		_errorExit( 'Could not read file %s' % filePath )

	langs= []
	devs= []

	lineNo= 0
	for lineIn in fh.readlines():
		lineNo+= 1
		line =lineIn.strip()
		if not line.startswith("#"):
			if len( line ) > 0:
				fields = line .split ( fieldSep )
				# _dbx( len( fields ) )
				if len ( fields ) != 2:

					_errorExit( "Each payload line in '%s' is must contain 2 fields separated by '%s'. Line %d is invalid" % ( filePath, fieldSep, lineNo) )

				key, value = fields[0:2] # start from 0 and take 2
				if key == devLiteral :
					if value in devs :
						_errorExit( "Device %s found again in line %d. Dupes are not permitted!" % (value, lineNo) )
					devs.append( value )
				elif key == langLiteral :
					if value in langs :
						_errorExit( "Device %s found again in line %d. Dupes are not permitted!" % (value, lineNo) )
					langs.append( value )
				else:
					_errorExit( "The keyword found in line %d of '%s' is invalid" % ( lineNo, filePath ) )

	return devs, langs

def performBuild ( projectDir, buildOutputDir, doClean = True ):
	""" A wrapper around `xcodebuild` that tells it to build the app in the temp
	directory. If your app uses workspaces or special schemes, you'll need to
	specify them here.
	
	Use `man xcodebuild` for more information on how to build your project.
	"""

	xcworkspaceFiles = glob.glob( '%s/*.xcworkspace' % projectDir )
	if len( xcworkspaceFiles ) > 0 :
		_errorExit ( "Found at least one xcworkspace files in '%s'. Building with xcworkspace is not yet supported!" % projectDir )

	cmdArgs = [ 'xcodebuild'
		, '-sdk', 'iphonesimulator'
		, 'CONFIGURATION_BUILD_DIR=' + buildOutputDir
		, 'PRODUCT_NAME=' + 'app'
		]

	
	if doClean: 
		_infoTs( "Building with __clean__ ..." , True )
		cmdArgs.append( 'clean' )
	else :
		_infoTs( "Building without __clean__ ..."  )
	cmdArgs.append( 'build' )

	_debug( "cmnd: %s" % cmdArgs.join(" ") )
	_debug( "returning without calling xcodebuild" ); 			return

	savedDir = os.getcwd()
	os.chdir( projectDir )
	subprocess.check_call ( cmdArgs )
	os.chdir( savedDir )

def mkdir ( path ):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
		raise
 
def rmdirAskConditionally( path, dirUsage ):
	if os.path.isdir( path ):
		if not path.startswith( '/tmp/' ):
			answer = raw_input( "Non-temp directory '%s' used for %s already exists. Enter 'yes' to proceed for removal or anything else to abort: " % path, dirUsage )
			if answer == 'yes':
				None # back to common path
			else:
				_errorExit( "Script aborted to retain directory '%s' " % path )

		shutil.rmtree( path )
	else:
		_dbx( "'%s' does not exist" % path )

def assertScreenshotsBackupRoot ( path ):
	if os.path.isdir( path ):
		answer = raw_input( "Directory '%s' already exists. Enter 'yes' to proceed for removal or anything else to abort: " % path )
		if answer == 'yes':
			shutil.rmtree( path )
		else:
			_errorExit( 'Script aborted.')
			
	mkdir( path )

def backupScreenshots( srcRoot, tgtRoot, lang, dev ):
	"""
    Since we always clear out the trace results before every run, we can
    assume that any screenshots were saved in the "Run 1" directory. Copy them
    to the screenshotsBackupLoc's language folder!
	"""
	tgtDir = os.path.join( tgtRoot, makeExpandFriendlyPath( dev ), lang )
	mkdir( tgtDir )

	cntFiles = 0
	cntRotated = 0
	srcDir = os.path.join( srcRoot, 'Run 1' )
	_dbx( "Copying png files from '%s' to '%s' ..." % ( srcDir, tgtDir ) )
	for file in glob.glob( srcDir + '/*.png' ):
		if file.find( 'landscape' ) >= 0 :
			subprocess.check_call( [ 'sips', '-r', '-90', file ] )
			cntRotated += 1
		shutil.copy( file, tgtDir )
		cntFiles += 1
	_dbx( "Files rotated: %d, copied: '%d'" % ( cntRotated, cntFiles ) )

def makeExpandFriendlyPath( string ):
	# replace round brackets characters and space with underscore
	return re.sub(  '[\(\) ]', '_', string )

def main():
	scriptBasename = os.path.basename( __file__ )
	argObject = parseCmdLine()

	screenshotsArchiveRoot = argObject.screenshotsArchiveRoot 

	# we check dir backup directory at this early stage so not too time is wasted when user does
	# want to keep the content of the target directory
	assertScreenshotsBackupRoot ( screenshotsArchiveRoot )
	_infoTs( "Screenshots will be backed up to '%s'" % screenshotsArchiveRoot )

	devs, langs = getListOfLangsAndDevicesFromFile ( './listOfLangsAndDevices.txt' )
	_infoTs( 'Will iterate over these lang(s) : \t%s' % '; '.join( langs ) )
	_infoTs( 'Will iterate over these dev(s) : \t%s'  % '; '.join( devs ) )

	performBuild( argObject.project_dir, argObject.BuildTestOutput, argObject.cleanSwitch )

	for dev in devs:
		for lang in langs:

			deployAppToDeviceAndSetLang( lang= lang, dev= dev )
			startUITestTarget( outputDir= outputDir )
			backupScreenshots( sourceDir= sourceDir, targetDir= backupDir, lang= lang, dev= dev )

			_infoTs( "Done with simulator %s and lang %s" % ( dev, lang ) )

	_infoTs( "\n\n%s completed normally." % scriptBasename , True )
			
main()

