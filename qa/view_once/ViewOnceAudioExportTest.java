package com.waenhancer.xposed.features.media;

import android.content.*;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public final class ViewOnceAudioExportTest {
    // FFmpeg/libopus-generated 40 ms silence, 48 kHz, 16 kb/s CBR, mono/stereo.
    // Decodable fixture containers, not host samples or a production decoder test.
    static final String MONO="T2dnUwACAAAAAAAAAADoIsDbAAAAANQ9mxgBE09wdXNIZWFkAQE4AYC7AAAAAABPZ2dTAAAAAAAAAAAAAOgiwNsBAAAAv+Wg6QE+T3B1c1RhZ3MNAAAATGF2ZjYwLjE2LjEwMAEAAAAdAAAAZW5jb2Rlcj1MYXZjNjAuMzEuMTAyIGxpYm9wdXNPZ2dTAAS4CAAAAAAAAOgiwNsCAAAAP6z2yAMoKCh4C+RVxnTZjM6286+6Es8/J3PqpGB0d1xgCuc6HRmVKEPM+88DxC4AeAbjcifhROpV8fDA1d4erlHn2xW4xMoAh3jRNPw/ZHPu8abdNvnMAHgG43nIyVfAohIj+u9n8y8boLbIQvlRECD50Ujn9E0pIGrA2TwrZAA=";
    static final String STEREO="T2dnUwACAAAAAAAAAADxUAWoAAAAAMs4qy0BE09wdXNIZWFkAQI4AYC7AAAAAABPZ2dTAAAAAAAAAAAAAPFQBagBAAAAnyDjwAE+T3B1c1RhZ3MNAAAATGF2ZjYwLjE2LjEwMAEAAAAdAAAAZW5jb2Rlcj1MYXZjNjAuMzEuMTAyIGxpYm9wdXNPZ2dTAAS4CAAAAAAAAPFQBagCAAAA9hT3VgMoKCh4C+RVxnTZjM6286+6Es8/J3PqpGB0d1xgCuc6HRmVKEPM+88DxC4AeAbjcifhROpV8fDA1d4erlHn2xW4xMoAh3jRNPw/ZHPu8abdNvnMAHgG43nIyVfAohIj+u9n8y8boLbIQvlRECD50Ujn9E0pIGrA2TwrZAA=";
    static int checks;
    static void check(String label,boolean value){if(!value)throw new AssertionError(label);checks++;}
    static void export(ContentResolver resolver,File source)throws IOException{
        AudioEntryPoint.export(new Context(resolver),source);
    }
    static void success(ContentResolver resolver,File source,byte[] bytes)throws IOException{
        boolean complete=true;
        try{export(resolver,source);}catch(IOException rejected){complete=false;}
        check("Recognized Opus audio can be exported",complete);
        check("Audio collection selected",resolver.collections.get(0).toString().equals("audio"));
        check("Audio MIME selected",resolver.inserted.get(0).get("mime").equals("audio/ogg"));
        check("Audio goes to Music/WAEX",resolver.inserted.get(0).get("path").equals("Music/WAEX"));
        check("Opus extension is content-derived",((String)resolver.inserted.get(0).get("name")).endsWith(".opus"));
        check("Audio bytes unchanged",Arrays.equals(resolver.copied,bytes));
        check("Audio hidden until fully closed",resolver.pendingDuringWrite&&resolver.publishAfterClose&&resolver.updates==1&&!resolver.deleted);
    }
    static void rejected(File source,byte[] bytes,String label)throws Exception{
        Files.write(source.toPath(),bytes);ContentResolver resolver=new ContentResolver();boolean rejected=false;
        try{export(resolver,source);}catch(IOException expected){rejected=true;}
        check("Unsupported audio rejected: "+label,rejected);
        check("Unsupported audio never creates a row: "+label,resolver.creates==0);
    }
    public static void main(String[] args)throws Exception{
        File dir=new File(args[0]);check("Fixture folder",dir.mkdirs());Environment.root=dir;
        byte[] mono=Base64.getDecoder().decode(MONO),stereo=Base64.getDecoder().decode(STEREO);
        File source=new File(dir,"misleading-private-name.mp4");
        for(byte[] bytes:new byte[][]{mono,stereo}){
            Files.write(source.toPath(),bytes);success(new ContentResolver(),source,bytes);
        }
        Files.write(source.toPath(),mono);ContentResolver separate=new ContentResolver();boolean refused=false;
        try{GalleryMediaExporter.export(new Context(separate),source);}catch(IOException expected){refused=true;}
        check("Gallery route cannot publish audio",refused&&separate.creates==0);
        ContentResolver repeated=new ContentResolver();export(repeated,source);export(repeated,source);
        check("Audio names unique",!repeated.inserted.get(0).get("name").equals(repeated.inserted.get(1).get("name")));
        byte[] jpeg=new byte[]{(byte)255,(byte)216,(byte)255,12,13};
        rejected(source,jpeg,"JPEG is not voice");
        byte[] mp4=new byte[32];System.arraycopy("ftypisom".getBytes(java.nio.charset.StandardCharsets.US_ASCII),0,mp4,4,8);
        rejected(source,mp4,"MP4 is not proof of supported voice");
        for(int[] mutation:new int[][]{{0,0},{4,1},{5,0},{5,3},{6,1},{13,1},{18,1},{21,1},
                {26,0},{26,2},{27,18},{27,20},{28,0},{36,0},{36,2},{36,16},{37,0},{37,3},{46,1}}){
            byte[] bytes=mono.clone();bytes[mutation[0]]=(byte)mutation[1];
            rejected(source,bytes,"header byte "+mutation[0]+" value "+mutation[1]);
        }
        byte[] vorbis=mono.clone();System.arraycopy("vorbis!!".getBytes(java.nio.charset.StandardCharsets.US_ASCII),0,vorbis,28,8);
        rejected(source,vorbis,"generic Ogg/Vorbis is not Opus");
        for(int length:new int[]{0,3,27,46})rejected(source,Arrays.copyOf(mono,length),"truncated "+length);
        Files.write(source.toPath(),mono);
        for(String fault:List.of("nullInsert","nullOutput","failWrite","failFlush","failClose","failUpdate","failDelete")){
            ContentResolver resolver=new ContentResolver();ContentResolver.class.getField(fault).setBoolean(resolver,true);
            if(fault.equals("failDelete"))resolver.failWrite=true;
            boolean failed=false;try{export(resolver,source);}catch(Exception expected){failed=true;}
            check("Audio error is not success: "+fault,failed);
            check("Audio partial row cleanup attempted: "+fault,resolver.creates==0||resolver.deleted);
        }
        ContentResolver replacement=new ContentResolver(){
            @Override public Uri insert(Uri uri,ContentValues values){
                try{Files.move(source.toPath(),new File(dir,"original.opus").toPath());Files.write(source.toPath(),jpeg);}
                catch(IOException error){throw new AssertionError(error);}
                return super.insert(uri,values);
            }
        };
        success(replacement,source,mono);
        check("A replaced source path was not reopened",Arrays.equals(jpeg,Files.readAllBytes(source.toPath())));
        Files.write(source.toPath(),stereo);Build.VERSION.SDK_INT=28;export(new ContentResolver(),source);
        File[] saved=new File(dir,"Music/WAEX").listFiles();
        check("Legacy audio publishes one final Opus file",saved!=null&&saved.length==1&&saved[0].getName().endsWith(".opus"));
        check("Legacy audio preserves bytes",Arrays.equals(stereo,Files.readAllBytes(saved[0].toPath())));
        check("Legacy scanner receives audio MIME",MediaScannerConnection.scans==1&&MediaScannerConnection.mimes[0].equals("audio/ogg"));
        check("Legacy scanner receives final path",MediaScannerConnection.paths[0].equals(saved[0].getAbsolutePath()));
        System.out.println("PASS: "+checks+" real audio header, storage, descriptor and copy checks (Android storage doubles)");
    }
}
