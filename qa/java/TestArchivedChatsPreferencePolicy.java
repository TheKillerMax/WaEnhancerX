package com.waenhancer.xposed.features.privacy;

public final class TestArchivedChatsPreferencePolicy {
    private static int count;
    private static void check(boolean result,String description){count++;if(!result)throw new AssertionError(description);}
    public static void main(String[] args) {
        Object[] on={"1","true","TRUE","2",Boolean.TRUE,1,2L,"yes"};
        Object[] off={null,"0","false","FALSE","  ","",Boolean.FALSE,0,0L,new Object()};
        for(Object value:on) check(ArchivedChatsPreferencePolicy.isHidden(value),"valid hide state: "+value);
        for(Object value:off) check(!ArchivedChatsPreferencePolicy.isHidden(value),"valid visible state: "+value);
        check(ArchivedChatsPreferencePolicy.isHidden(" 1 "),"whitespace trimmed");
        check(!ArchivedChatsPreferencePolicy.isHidden(" False "),"case and whitespace normalized");
        System.out.println("PASS: "+count+" typed archive visibility assertions");
    }
}
