/* This program is meant to scan the output from swift compiler and list errors and optionally 
warning. The reason why I don't want to look at the xcodebuild output directly is because 
its output is too long and it takes time to scroll back and to find the relevant stuff.
There may be a lot of warnings and at times I want to focus on errors first.

I chose swift with the intention to get more proficient in this language

To compile run command: swiftc LsCompileIssues.swift -o LsCompileIssues && ./LsCompileIssues 
*/

import Foundation

func _dbx( _ text: String ) { print( "dbx: \(text)" ) }

class Helper {
	static func getSettings ( ) -> (
		String // compiler output path
		,Bool // list warning
		// for the future number of errors
		)
	{ 
		var inputPath : String?
		var listWarnings = false
	
		// try environment variables first which have a low prio
		let envVarDict = ProcessInfo.processInfo.environment
		let keyInputPath = "compilerIssuesPath"
		if let varValue = envVarDict[keyInputPath] { 
			_dbx( "\(keyInputPath) is \(varValue)" ) 
			inputPath = varValue
		} 

		// now try line command arguments. Unfortunately the swift library does not something
		// as luxurious as argparse, not even getops, yet

		for (ix, arg) in CommandLine.arguments.enumerated() {
			_dbx("ix: \(ix)")
			_dbx("arg: \(arg)")
			switch ix {
				case 0: break // this very program 
				case 1: inputPath = arg
				case 2: 
					if arg.uppercased() == "Y" {
						listWarnings = true
					}
				default: print( "will ignore excess argument '\(arg)'" )
			}
		}
		if inputPath == nil {
			fatalError( "path of file with compiler issues must be given as 1. argument")
		}
		return (inputPath!, listWarnings)
	}

	static func readLinesFromFile ( path: String ) -> [String] {
		var lines = [String]() 
		do {
			let data = try String(contentsOfFile: path, encoding: .utf8)
			lines = data.components(separatedBy: .newlines)
		} catch {
			fatalError( error.localizedDescription )
	   }
		return lines
	}
} //Helper

//MARK: CompileIssue 
class CompileIssue {
	enum FsmStates {
		case initial
		, srcLineExpected, srcPinExpected
		, noteMsgExpected, refLineExpected, refPinExpected
	}

	static let errMsgPattern = "\\d+:\\d+: error:"
	static let errMsgRegex = try! NSRegularExpression( pattern: errMsgPattern, options: [] ) //we seem to foresake error handling and accept automatic abort

	static func doesMatchAtMostOnce( regexEngine: NSRegularExpression, string: String ) -> Bool {
		var cntMatch = 0
		regexEngine.enumerateMatches( in: string ,options: []
			,range: NSRange( location: 0, length: string.characters.count ) )
		{ //closure or match handler
			(match, _, stop) in  
			cntMatch += 1
			if cntMatch > 1 { 
					fatalError( "Found more than 1 match for '\(regexEngine.pattern)' in following line!\n\(string)") 
			}
		}
		return cntMatch <= 1
	}

	public var errMsg = String()
	public var srcLine = String()
	public var srcPin = String()
	public var noteMsg = String()
	public var refLine = String()
	public var refPin = String()

	init( errMsg: String ) { self.errMsg = errMsg }

}

let (inputPath, listWarnings) = Helper.getSettings()
_dbx( "inputPath: \(inputPath)" )
_dbx("listWarnings: \(listWarnings)")
let lines = Helper.readLinesFromFile ( path: inputPath )


var fsmState = CompileIssue.FsmStates.initial 
for (lno, lnText) in lines.enumerated() {
	_dbx("lno: \(lno)")
	//for debugging print line begin
	let indexMonkey /*bcos the index concept is monkey-like*/ = lnText.characters.count > 80 
			? lnText.index( lnText.startIndex, offsetBy: 80 ) 
			: lnText.index( lnText.startIndex, offsetBy: lnText.characters.count ) 
	let textChunk = lnText.substring( to: indexMonkey )
	_dbx("textChunk: \(textChunk)")

/* examples of issues: 

Type 1 (3 lines msg,sourceLine,pointer):

	/Users/bmlam/Dropbox/my-apps/MountainsAround/MountainsAround/RootViewController.swift:50:4: error: expected '{' to start the body of for-each loop
                        self.mapView.addAnnotation( pin )
                        ^
Type 2 (5 lines msg,sourceLine,pointer,note,referencedLine,pointer):

/Users/bmlam/Dropbox/my-apps/MountainsAround/MountainsAround/RootViewController.swift:49:14: error: use of unresolved identifier 'mountainPin'
                for pin in mountainPin//s {
                           ^~~~~~~~~~~
	/Users/bmlam/Dropbox/my-apps/MountainsAround/MountainsAround/Global.swift:4:5: note: did you mean 'mountainPins'?
var mountainPins = [MyPin]()
    ^

For type 1: we store sourceLine and pointer as one property
For type 2: we store the note,referencedLine,pointer as one property

*/
	var issues = [CompileIssue]()
	switch fsmState {
		case .initial :
			if CompileIssue.doesMatchAtMostOnce( regexEngine: CompileIssue.errMsgRegex, string: lnText ) {
				fsmState = CompileIssue.FsmStates.srcLineExpected
				issues.append( CompileIssue( errMsg: lnText ) )
			}
		case .srcLineExpected:		_dbx("line: \(#line)")
		case .srcPinExpected:		_dbx("line: \(#line)")
		case .noteMsgExpected: 		_dbx("line: \(#line)")
		case .refLineExpected: 		_dbx("line: \(#line)")
		case .refPinExpected:		_dbx("line: \(#line)")

	} //switch

	_dbx("issues.count: \(issues.count)")
}

// print("xyz: \(xyz)")
// _dbx("xyz: \(xyz)")
// _dbx("line: \(#line)")
