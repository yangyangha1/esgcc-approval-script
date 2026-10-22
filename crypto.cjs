const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
let input='';process.stdin.on('data',d=>input+=d);process.stdin.on('end',()=>{
 const a=JSON.parse(input);
 const sandbox={navigator:{appName:'Netscape',appVersion:'5',userAgent:'Mozilla/5.0 Firefox/130'},crypto:crypto.webcrypto};
 sandbox.window=sandbox;
 vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync(__dirname+'/vendor/smcrypt.js','utf8'),sandbox,{timeout:3000});
 const digest=crypto.createHash('md5').update(a.password).digest('hex').toUpperCase();
 sandbox.digest=digest;sandbox.publicKey=a.publicKey;
 const value=vm.runInContext('SG_sm2Encrypt(digest,publicKey)',sandbox,{timeout:5000});
 process.stdout.write(value);
});
