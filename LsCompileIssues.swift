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
		case initial, gotErrMsg, gotSrcCode, gotNote
	}
	var errMsg = String()
	var srcCode = String()
	var note = String()

	func setErrMsg ( _ arg: String ) { self.errMsg = arg }
	func setSrcCode( _ arg: String ) { self.srcCode = arg }
	func setNote   ( _ arg: String ) { self.note = arg }
}

let (inputPath, listWarnings) = Helper.getSettings()
_dbx( "inputPath: \(inputPath)" )
_dbx("listWarnings: \(listWarnings)")
let lines = Helper.readLinesFromFile ( path: inputPath )

let errMsgPattern = "\\d+:\\d+: error:"
let errMsgRegex = try! NSRegularExpression( pattern: errMsgPattern, options: [] ) //we seem to foresake error handling and accept automatic abort

var fsmState = CompileIssue.FsmStates.initial 
for (lno, lnText) in lines.enumerated() {
	_dbx("lno: \(lno)")
	let indexMonkey /*bcos the index concept is monkey-like*/ = lnText.characters.count > 80 
			? lnText.index( lnText.startIndex, offsetBy: 80 ) 
			: lnText.index( lnText.startIndex, offsetBy: lnText.characters.count ) 
	let textChunk = lnText.substring( to: indexMonkey )
	_dbx("textChunk: \(textChunk)")
	switch fsmState {
		case .initial :
			errMsgRegex.enumerateMatches( in: lnText ,options: []
				,range: NSRange( location: 0, length: lnText.characters.count ) )
			{ //closure or match handler
				(macth, _, stop) in  
				
				fsmState = CompileIssue.FsmStates.gotErrMsg 
				
			}
		default: break
	} //switch
}

// print("xyz: \(xyz)")
// _dbx("xyz: \(xyz)")
